Imports TestProject

Namespace TestProject.Models
    Public Class Person
        Public Property Name As String
        Public Property Age As Integer
        Public Property Email As String

        Public Sub New(name As String, age As Integer, email As String)
            Me.Name = name
            Me.Age = age
            Me.Email = email
        End Sub

        Public Overrides Function ToString() As String
            Return $"{Name} ({Age}) - {Email}"
        End Function

        Public Function IsAdult() As Boolean
            Return Age >= 18
        End Function

        Public Function CalculateYearsUntilRetirement() As Integer
            Dim calculator As New Calculator()
            Return calculator.Subtract(65, Age)
        End Function
    End Class
End Namespace
