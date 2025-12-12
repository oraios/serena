interface IPaymentProcessor
{
    procedure ProcessPayment(Customer: Record "TEST Customer"): Boolean;
    procedure ValidatePaymentMethod(PaymentMethodCode: Code[10]): Boolean;
    procedure GetTransactionFee(Amount: Decimal): Decimal;
    procedure RefundPayment(TransactionID: Text[50]): Boolean;
}