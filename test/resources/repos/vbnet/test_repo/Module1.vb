Imports System

Namespace TestProject
    Module Module1
        Sub Main(args As String())
            Console.WriteLine("Hello, World!")

            Dim calculator As New Calculator()
            Dim result As Integer = calculator.Add(5, 3)
            Console.WriteLine($"5 + 3 = {result}")
        End Sub
    End Module

    Public Class Calculator
        Public Function Add(a As Integer, b As Integer) As Integer
            Return a + b
        End Function

        Public Function Subtract(a As Integer, b As Integer) As Integer
            Return a - b
        End Function

        Public Function Multiply(a As Integer, b As Integer) As Integer
            Return a * b
        End Function

        Public Function Divide(a As Integer, b As Integer) As Double
            If b = 0 Then
                Throw New DivideByZeroException("Cannot divide by zero")
            End If
            Return CDbl(a) / b
        End Function
    End Class
End Namespace
