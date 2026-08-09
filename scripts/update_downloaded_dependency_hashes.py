from sensai.util import logging

from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS
from solidlsp.language_servers.kotlin_language_server import KotlinLanguageServer
from solidlsp.language_servers.nextflow_language_server import NextflowLanguageServer

if __name__ == "__main__":
    logging.configure()
    EclipseJDTLS.DependencyProvider.update_dep_hashes()
    NextflowLanguageServer.DependencyProvider.update_dep_hashes()
    KotlinLanguageServer.DependencyProvider.update_dep_hashes()
