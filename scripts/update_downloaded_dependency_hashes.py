from sensai.util import logging

from solidlsp.language_servers.eclipse_jdtls import EclipseJDTLS

if __name__ == "__main__":
    logging.configure()
    EclipseJDTLS.DependencyProvider.update_dep_hashes()
