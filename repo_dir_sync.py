# -*- coding: utf-8 -*-
import glob
import os
import shutil
from subprocess import Popen, PIPE
import re
import sys
from typing import List, Optional, Sequence
import platform


def popen(cmd):
    shell = platform.system() != "Windows"
    p = Popen(cmd, shell=shell, stdin=PIPE, stdout=PIPE)
    return p


def call(cmd):
    p = popen(cmd)
    return p.stdout.read().decode("utf-8")


def execute(cmd, exceptionOnError=True):
    """
    :param cmd: the command to execute
    :param exceptionOnError: if True, raise on exception on error (return code not 0); if False return
        whether the call was successful
    :return: True if the call was successful, False otherwise (if exceptionOnError==False)
    """
    p = popen(cmd)
    p.wait()
    success = p.returncode == 0
    if exceptionOnError:
        if not success:
            raise Exception("Command failed: %s" % cmd)
    else:
        return success


def gitLog(path, arg):
    oldPath = os.getcwd()
    os.chdir(path)
    lg = call("git log --no-merges " + arg)
    os.chdir(oldPath)
    return lg


def gitCommit(msg):
    with open(COMMIT_MSG_FILENAME, "wb") as f:
        f.write(msg.encode("utf-8"))
    gitCommitWithMessageFromFile(COMMIT_MSG_FILENAME)


def gitCommitWithMessageFromFile(commitMsgFilename):
    if not os.path.exists(commitMsgFilename):
        raise FileNotFoundError(f"{commitMsgFilename} not found in {os.path.abspath(os.getcwd())}")
    os.system(f"git commit --file={commitMsgFilename}")
    os.unlink(commitMsgFilename)


COMMIT_MSG_FILENAME = "commitmsg.txt"


class OtherRepo:
    SYNC_COMMIT_ID_FILE_LIB_REPO = ".syncCommitId.remote"
    SYNC_COMMIT_ID_FILE_THIS_REPO = ".syncCommitId.this"
    SYNC_COMMIT_MESSAGE = f"Updated %s sync commit identifiers"
    SYNC_BACKUP_DIR = ".syncBackup"
    
    def __init__(self, name, branch, pathToLib):
        self.pathToLibInThisRepo = os.path.abspath(pathToLib)
        if not os.path.exists(self.pathToLibInThisRepo):
            raise ValueError(f"Repository directory '{self.pathToLibInThisRepo}' does not exist")
        self.name = name
        self.branch = branch
        self.libRepo: Optional[LibRepo] = None

    def isSyncEstablished(self):
        return os.path.exists(os.path.join(self.pathToLibInThisRepo, self.SYNC_COMMIT_ID_FILE_LIB_REPO))
    
    def lastSyncIdThisRepo(self):
        with open(os.path.join(self.pathToLibInThisRepo, self.SYNC_COMMIT_ID_FILE_THIS_REPO), "r") as f:
            commitId = f.read().strip()
        return commitId

    def lastSyncIdLibRepo(self):
        with open(os.path.join(self.pathToLibInThisRepo, self.SYNC_COMMIT_ID_FILE_LIB_REPO), "r") as f:
            commitId = f.read().strip()
        return commitId

    def gitLogThisRepoSinceLastSync(self):
        lg = gitLog(self.pathToLibInThisRepo, '--name-only HEAD "^%s" .' % self.lastSyncIdThisRepo())
        lg = re.sub(r'commit [0-9a-z]{8,40}\n.*\n.*\n\s*\n.*\n\s*(\n.*\.syncCommitId\.(this|remote))+', r"", lg, flags=re.MULTILINE)  # remove commits with sync commit id update
        indent = "  "
        lg = indent + lg.replace("\n", "\n" + indent)
        return lg

    def gitLogLibRepoSinceLastSync(self, libRepo: "LibRepo"):
        syncIdFile = os.path.join(self.pathToLibInThisRepo, self.SYNC_COMMIT_ID_FILE_LIB_REPO)
        if not os.path.exists(syncIdFile):
            return ""
        with open(syncIdFile, "r") as f:
            syncId = f.read().strip()
        lg = gitLog(libRepo.libPath, '--name-only HEAD "^%s" .'  % syncId)
        lg = re.sub(r"Sync (\w+)\n\s*\n", r"Sync\n\n", lg, flags=re.MULTILINE)
        indent = "  "
        lg = indent + lg.replace("\n", "\n" + indent)
        return "\n\n" + lg

    def _userInputYesNo(self, question) -> bool:
        result = None
        while result not in ("y", "n"):
            result = input(question + " [y|n]: ").strip()
        return result == "y"

    def pull(self, libRepo: "LibRepo"):
        """
        Pulls in changes from this repository into the lib repo
        """
        # switch to branch in lib repo
        os.chdir(libRepo.rootPath)
        execute("git checkout %s" % self.branch)

        # check if the branch contains the commit that is referenced as the remote commit
        remoteCommitId = self.lastSyncIdLibRepo()
        remoteCommitExists = execute("git rev-list HEAD..%s" % remoteCommitId, exceptionOnError=False)
        if not remoteCommitExists:
            if not self._userInputYesNo(f"\nWARNING: The referenced remote commit {remoteCommitId} does not exist "
                                        f"in your {self.libRepo.name} branch '{self.branch}'!\nSomeone else may have "
                                        f"pulled/pushed in the meantime.\nIt is recommended that you do not continue. "
                                        f"Continue?"):
                return

        # check if this branch is clean
        lgLib = self.gitLogLibRepoSinceLastSync(libRepo).strip()
        if lgLib != "":
            print(f"The following changes have been added to this branch in the library:\n\n{lgLib}\n\n")
            print(f"ERROR: You must push these changes before you can pull or reset this branch to {remoteCommitId}")
            sys.exit(1)

        # get log with relevant commits in this repo that are to be pulled
        lg = self.gitLogThisRepoSinceLastSync()

        os.chdir(libRepo.rootPath)

        # create commit message file
        commitMsg = f"Sync {self.name}\n\n" + lg
        with open(COMMIT_MSG_FILENAME, "w") as f:
            f.write(commitMsg)

        # ask whether to commit these changes
        print("Relevant commits:\n\n" + lg + "\n\n")
        if not self._userInputYesNo(f"The above changes will be pulled from {self.name}.\n"
                f"You may change the commit message by editing {os.path.abspath(COMMIT_MSG_FILENAME)}.\n"
                "Continue?"):
            os.unlink(COMMIT_MSG_FILENAME)
            return

        # prepare restoration of ignored files
        self.prepare_restoration_of_ignored_files(libRepo.rootPath)

        # remove library tree in lib repo
        shutil.rmtree(self.libRepo.libDirectory)

        # copy tree from this repo to lib repo (but drop the sync commit id files)
        shutil.copytree(self.pathToLibInThisRepo, self.libRepo.libDirectory)
        for fn in (self.SYNC_COMMIT_ID_FILE_LIB_REPO, self.SYNC_COMMIT_ID_FILE_THIS_REPO):
            p = os.path.join(self.libRepo.libDirectory, fn)
            if os.path.exists(p):
                os.unlink(p)

        # restore ignored directories/files
        self.restore_ignored_files(libRepo.rootPath)

        # make commit in lib repo
        os.system("git add %s" % self.libRepo.libDirectory)
        gitCommitWithMessageFromFile(COMMIT_MSG_FILENAME)
        newSyncCommitIdLibRepo = call("git rev-parse HEAD").strip()

        # update commit ids in this repo
        os.chdir(self.pathToLibInThisRepo)
        newSyncCommitIdThisRepo = call("git rev-parse HEAD").strip()
        with open(self.SYNC_COMMIT_ID_FILE_LIB_REPO, "w") as f:
            f.write(newSyncCommitIdLibRepo)
        with open(self.SYNC_COMMIT_ID_FILE_THIS_REPO, "w") as f:
            f.write(newSyncCommitIdThisRepo)
        execute('git add %s %s' % (self.SYNC_COMMIT_ID_FILE_LIB_REPO, self.SYNC_COMMIT_ID_FILE_THIS_REPO))
        execute(f'git commit -m "{self.SYNC_COMMIT_MESSAGE % self.libRepo.name} (pull)"')

        print(f"\n\nIf everything was successful, you should now push your changes to branch "
              f"'{self.branch}'\nand get your branch merged into develop (issuing a pull request where appropriate)")
        
    def push(self, libRepo: "LibRepo"):
        """
        Pushes changes from the lib repo to this repo
        """
        os.chdir(libRepo.rootPath)

        # switch to the source repo branch
        execute(f"git checkout {self.branch}")

        if self.isSyncEstablished():

            # check if there are any commits that have not yet been pulled
            unpulledCommits = self.gitLogThisRepoSinceLastSync().strip()
            if unpulledCommits != "":
                print(f"\n{unpulledCommits}\n\n")
                if not self._userInputYesNo(f"WARNING: The above changes in repository '{self.name}' have not"
                                            f" yet been pulled.\nYou might want to pull them.\n"
                                            f"If you continue with the push, they will be lost. Continue?"):
                    return

            # get change log in lib repo since last sync
            libLogSinceLastSync = self.gitLogLibRepoSinceLastSync(libRepo)

            print("Relevant commits:\n\n" + libLogSinceLastSync + "\n\n")
            if not self._userInputYesNo("The above changes will be pushed. Continue?"):
                return
            print()
        else:
            libLogSinceLastSync = ""

        # prepare restoration of ignored files in target repo
        base_dir_this_repo = os.path.join(self.pathToLibInThisRepo, "..")
        self.prepare_restoration_of_ignored_files(base_dir_this_repo)

        # remove the target repo tree and update it with the tree from the source repo
        shutil.rmtree(self.pathToLibInThisRepo)
        shutil.copytree(libRepo.libPath, self.pathToLibInThisRepo)

        # get the commit id of the source repo we just copied
        commitId = call("git rev-parse HEAD").strip()

        # restore ignored directories and files
        self.restore_ignored_files(base_dir_this_repo)

        # go to the target repo
        os.chdir(self.pathToLibInThisRepo)

        # commit new version in this repo
        execute("git add .")
        with open(self.SYNC_COMMIT_ID_FILE_LIB_REPO, "w") as f:
            f.write(commitId)
        execute("git add %s" % self.SYNC_COMMIT_ID_FILE_LIB_REPO)
        gitCommit(f"{self.libRepo.name} {commitId}" + libLogSinceLastSync)
        commitId = call("git rev-parse HEAD").strip()

        # update information on the commit id we just added
        with open(self.SYNC_COMMIT_ID_FILE_THIS_REPO, "w") as f:
            f.write(commitId)
        execute("git add %s" % self.SYNC_COMMIT_ID_FILE_THIS_REPO)
        execute(f'git commit -m "{self.SYNC_COMMIT_MESSAGE % self.libRepo.name} (push)"')

        os.chdir(libRepo.rootPath)
        
        print(f"\n\nIf everything was successful, you should now update the remote branch:\ngit push")

    def prepare_restoration_of_ignored_files(self, base_dir: str):
        """
        :param base_dir: the directory containing the lib directory, to which ignored paths are relative
        """
        cwd = os.getcwd()
        os.chdir(base_dir)

        # ensure backup dir exists and is empty
        if os.path.exists(self.SYNC_BACKUP_DIR):
            shutil.rmtree(self.SYNC_BACKUP_DIR)
        os.mkdir(self.SYNC_BACKUP_DIR)

        # backup ignored, unversioned directories
        for d in self.libRepo.fullyIgnoredUnversionedDirectories:
            if os.path.exists(d):
                shutil.copytree(d, os.path.join(self.SYNC_BACKUP_DIR, d))

        os.chdir(cwd)

    def restore_ignored_files(self, base_dir: str):
        """
        :param base_dir: the directory containing the lib directory, to which ignored paths are relative
        """
        cwd = os.getcwd()
        os.chdir(base_dir)

        # remove fully ignored directories that were overwritten by the sync
        for d in self.libRepo.fullyIgnoredVersionedDirectories + self.libRepo.fullyIgnoredUnversionedDirectories:
            if os.path.exists(d):
                print("Removing overwritten content: %s" % d)
                shutil.rmtree(d)

        # restore directories and files that can be restored via git
        for d in self.libRepo.ignoredDirectories + self.libRepo.fullyIgnoredVersionedDirectories:
            restoration_cmd = "git checkout %s" % d
            print("Restoring: %s" % restoration_cmd)
            os.system(restoration_cmd)
        for pattern in self.libRepo.ignoredFileGlobPatterns:
            for path in glob.glob(pattern, recursive=True):
                print("Restoring via git: %s" % path)
                os.system("git checkout %s" % path)

        # restore directories that were backed up
        for d in self.libRepo.fullyIgnoredUnversionedDirectories:
            if os.path.exists(os.path.join(self.SYNC_BACKUP_DIR, d)):
                print("Restoring from backup: %s" % d)
                shutil.copytree(os.path.join(self.SYNC_BACKUP_DIR, d), d)

        # remove backup dir
        shutil.rmtree(self.SYNC_BACKUP_DIR)

        os.chdir(cwd)


class LibRepo:
    def __init__(self, name: str, libDirectory: str,
            ignoredDirectories: Sequence[str] = (),
            fullyIgnoredVersionedDirectories: Sequence[str] = (),
            fullyIgnoredUnversionedDirectories: Sequence[str] = (),
            ignoredFileGlobPatterns: Sequence[str] = ()
    ):
        """
        :param name: name of the library being synced
        :param libDirectory: relative path to the library directory within this repo
        :param ignoredDirectories: ignored directories; existing files in ignored directories will be restored
            via 'git checkout' on pull/push, but new files will be added.
            This is useful for configuration-like files, where users may have local changes that should not
            be overwritten, but new files should still be added.
        :param fullyIgnoredVersionedDirectories:
            fully ignored versioned directories will be restored to original state after push/pull via git checkout
        :param fullyIgnoredUnversionedDirectories:
            fully ignored unversioned directories will be backed up and restored to original state after push/pull
        :param ignoredFileGlobPatterns: files matching ignored glob patterns will be restored via 'git checkout'
            on pull/push
        """
        self.name = name
        self.rootPath = os.path.abspath(os.path.dirname(os.path.realpath(__file__)))
        self.libDirectory = libDirectory
        self.libPath = os.path.join(self.rootPath, self.libDirectory)
        self.ignoredDirectories: List[str] = list(ignoredDirectories)
        self.fullyIgnoredVersionedDirectories: List[str] = list(fullyIgnoredVersionedDirectories)
        self.fullyIgnoredUnversionedDirectories: List[str] = list(fullyIgnoredUnversionedDirectories)
        self.ignoredFileGlobPatterns: List[str] = list(ignoredFileGlobPatterns)
        self.otherRepos: List[OtherRepo] = []

    def add(self, repo: OtherRepo):
        repo.libRepo = self
        self.otherRepos.append(repo)

    def runMain(self):
        repos = self.otherRepos
        args = sys.argv[1:]
        if len(args) != 2:
            print(f"usage: sync.py <{'|'.join([repo.name for repo in repos])}> <push|pull>")
        else:
            repo = [r for r in repos if r.name == args[0]]
            if len(repo) != 1:
                raise ValueError(f"Unknown repo '{args[0]}'")
            repo = repo[0]

            if args[1] == "push":
                repo.push(self)
            elif args[1] == "pull":
                repo.pull(self)
            else:
                raise ValueError(f"Unknown command '{args[1]}'")
