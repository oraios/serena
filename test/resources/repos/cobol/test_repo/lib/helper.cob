*****************************************************************
      * HELPER - Helper program for testing cross-file references
      * Author: Serena Test Suite
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. HELPER.
       
       DATA DIVISION.
       LINKAGE SECTION.
       01  LS-MESSAGE        PIC X(50).
       
       PROCEDURE DIVISION USING LS-MESSAGE.
       HELPER-MAIN.
           MOVE "Hello from helper program!" TO LS-MESSAGE.
           PERFORM FORMAT-MESSAGE.
           GOBACK.
       
       FORMAT-MESSAGE.
           STRING "Formatted: " DELIMITED BY SIZE
                  LS-MESSAGE DELIMITED BY SIZE
                  INTO LS-MESSAGE.