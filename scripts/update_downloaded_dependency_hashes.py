from sensai.util import logging

from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS
from solidlsp.language_servers.kotlin_language_server import KotlinLanguageServer

if __name__ == "__main__":
    logging.configure()
    EclipseJDTLS.DependencyProvider.update_dep_hashes()
    KotlinLanguageServer.DependencyProvider.update_dep_hashes()
