import os
from repo_dir_sync import LibRepo, OtherRepo

r = LibRepo(name="serena", libDirectory="src")
r.add(OtherRepo(name="mux", branch="mux", pathToLib=os.path.join("..", "serena-multiplexer", "src-serena")))
r.runMain()
