*****************************************************************
      * CALCULATOR - Main COBOL program for testing
      * Author: Serena Test Suite
      *****************************************************************
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CALCULATOR.
       
       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-NUM1           PIC 9(4) VALUE 0.
       01  WS-NUM2           PIC 9(4) VALUE 0.
       01  WS-RESULT         PIC 9(8) VALUE 0.
       01  WS-GREETING       PIC X(50).
       
       PROCEDURE DIVISION.
       MAIN-PROCEDURE.
           MOVE 10 TO WS-NUM1.
           MOVE 20 TO WS-NUM2.
           
           PERFORM ADD-NUMBERS.
           DISPLAY "Result of addition: " WS-RESULT.
           
           PERFORM SUBTRACT-NUMBERS.
           DISPLAY "Result of subtraction: " WS-RESULT.
           
           PERFORM CALL-HELPER.
           
           STOP RUN.
       
       ADD-NUMBERS.
           ADD WS-NUM1 TO WS-NUM2 GIVING WS-RESULT.
       
       SUBTRACT-NUMBERS.
           SUBTRACT WS-NUM2 FROM WS-NUM1 GIVING WS-RESULT.
       
       CALL-HELPER.
           CALL 'HELPER' USING WS-GREETING.
           DISPLAY WS-GREETING.