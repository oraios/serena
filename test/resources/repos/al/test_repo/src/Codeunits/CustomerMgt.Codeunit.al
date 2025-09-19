codeunit 50000 CustomerMgt
{
    Permissions = tabledata "TEST Customer" = rimd;

    trigger OnRun()
    begin
        Message('Customer Management Codeunit');
    end;

    procedure CreateNewCustomer()
    var
        Customer: Record "TEST Customer";
        CustomerCard: Page "TEST Customer Card";
    begin
        Customer.Init();
        Customer.Insert(true);

        CustomerCard.SetRecord(Customer);
        CustomerCard.Run();
    end;

    procedure CreateCustomer(CustomerNo: Code[20]; CustomerName: Text[100]; CustomerType: Enum CustomerType): Boolean
    var
        Customer: Record "TEST Customer";
    begin
        if Customer.Get(CustomerNo) then
            exit(false);

        Customer.Init();
        Customer."No." := CustomerNo;
        Customer.Name := CustomerName;
        Customer."Customer Type" := CustomerType;
        Customer.UpdateSearchName();
        Customer.Insert(true);

        exit(true);
    end;

    procedure AssistEdit(var Customer: Record "TEST Customer"): Boolean
    var
        NoSeriesMgt: Codeunit NoSeriesManagement;
    begin
        with Customer do begin
            if NoSeriesMgt.SelectSeries(GetNoSeriesCode(), '', "No. Series") then begin
                NoSeriesMgt.SetSeries("No.");
                exit(true);
            end;
        end;
        exit(false);
    end;

    procedure TestNoSeries()
    var
        SalesSetup: Record "Sales & Receivables Setup";
    begin
        SalesSetup.Get();
        SalesSetup.TestField("Customer Nos.");
    end;

    procedure InitNo(var Customer: Record "TEST Customer")
    var
        NoSeriesMgt: Codeunit NoSeriesManagement;
    begin
        TestNoSeries();
        NoSeriesMgt.InitSeries(GetNoSeriesCode(), Customer."No. Series", 0D, Customer."No.", Customer."No. Series");
    end;

    procedure GetNoSeriesCode(): Code[20]
    var
        SalesSetup: Record "Sales & Receivables Setup";
    begin
        SalesSetup.Get();
        exit(SalesSetup."Customer Nos.");
    end;

    procedure CalculateTotalBalance(): Decimal
    var
        Customer: Record "TEST Customer";
        TotalBalance: Decimal;
    begin
        TotalBalance := 0;

        if Customer.FindSet() then
            repeat
                Customer.CalcFields(Balance);
                TotalBalance += Customer.Balance;
            until Customer.Next() = 0;

        exit(TotalBalance);
    end;

    procedure GetCustomerCount(CustomerType: Enum CustomerType): Integer
    var
        Customer: Record "TEST Customer";
    begin
        Customer.SetRange("Customer Type", CustomerType);
        exit(Customer.Count());
    end;

    procedure BlockCustomersOverCreditLimit()
    var
        Customer: Record "TEST Customer";
        BlockedCount: Integer;
    begin
        BlockedCount := 0;

        if Customer.FindSet() then
            repeat
                Customer.CalcFields(Balance);
                if (Customer."Credit Limit" > 0) and (Customer.Balance > Customer."Credit Limit") then begin
                    Customer.Blocked := true;
                    Customer.Modify(true);
                    BlockedCount += 1;
                end;
            until Customer.Next() = 0;

        if BlockedCount > 0 then
            Message('%1 customers blocked due to credit limit exceeded', BlockedCount);
    end;

    procedure GetPaymentProcessor(): Interface IPaymentProcessor
    var
        PaymentProcessorImpl: Codeunit PaymentProcessorImpl;
    begin
        exit(PaymentProcessorImpl);
    end;

    procedure SendCustomerStatement(CustomerNo: Code[20])
    var
        Customer: Record "TEST Customer";
        ReportSelections: Record "Report Selections";
    begin
        if not Customer.Get(CustomerNo) then
            Error('Customer %1 not found', CustomerNo);

        Customer.SetRecFilter();
        ReportSelections.SetRange(Usage, ReportSelections.Usage::"C.Statement");
        ReportSelections.PrintForCust(ReportSelections.Usage::"C.Statement", Customer, 1);
    end;

    procedure ValidateEmail(Email: Text[80]): Boolean
    var
        MailMgt: Codeunit "Mail Management";
    begin
        exit(MailMgt.CheckValidEmailAddress(Email));
    end;

    procedure MergeCustomers(FromCustomerNo: Code[20]; ToCustomerNo: Code[20])
    var
        FromCustomer: Record "TEST Customer";
        ToCustomer: Record "TEST Customer";
        CustomerLedgerEntry: Record "Cust. Ledger Entry";
    begin
        if not FromCustomer.Get(FromCustomerNo) then
            Error('Source customer %1 not found', FromCustomerNo);

        if not ToCustomer.Get(ToCustomerNo) then
            Error('Target customer %1 not found', ToCustomerNo);

        // Transfer ledger entries
        CustomerLedgerEntry.SetRange("Customer No.", FromCustomerNo);
        if CustomerLedgerEntry.FindSet() then
            repeat
                CustomerLedgerEntry."Customer No." := ToCustomerNo;
                CustomerLedgerEntry.Modify();
            until CustomerLedgerEntry.Next() = 0;

        // Delete source customer
        FromCustomer.Delete(true);

        Message('Customer %1 merged into %2', FromCustomerNo, ToCustomerNo);
    end;

    [EventSubscriber(ObjectType::Table, Database::"TEST Customer", OnAfterInsertEvent, '', true, true)]
    local procedure OnAfterInsertCustomer(var Rec: Record "TEST Customer")
    begin
        LogCustomerChange(Rec, 'INSERT');
    end;

    [EventSubscriber(ObjectType::Table, Database::"TEST Customer", OnAfterModifyEvent, '', true, true)]
    local procedure OnAfterModifyCustomer(var Rec: Record "TEST Customer")
    begin
        LogCustomerChange(Rec, 'MODIFY');
    end;

    local procedure LogCustomerChange(Customer: Record "TEST Customer"; ChangeType: Text[10])
    var
        ChangeLogEntry: Record "Change Log Entry";
    begin
        // Log customer changes for audit purposes
        ChangeLogEntry.Init();
        ChangeLogEntry."Table No." := Database::"TEST Customer";
        ChangeLogEntry."Primary Key Field 1 Value" := Customer."No.";
        ChangeLogEntry."Type of Change" := ChangeLogEntry."Type of Change"::Modification;
        ChangeLogEntry."User ID" := UserId;
        ChangeLogEntry."Date and Time" := CurrentDateTime;
        if ChangeLogEntry.Insert() then;
    end;
}