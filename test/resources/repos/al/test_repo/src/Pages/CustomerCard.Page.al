page 50001 "TEST Customer Card"
{
    Caption = 'Customer Card';
    PageType = Card;
    SourceTable = "TEST Customer";
    RefreshOnActivate = true;

    layout
    {
        area(Content)
        {
            group(General)
            {
                Caption = 'General';

                field("No."; Rec."No.")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer number.';

                    trigger OnAssistEdit()
                    begin
                        if CustomerMgt.AssistEdit(Rec) then
                            CurrPage.Update();
                    end;
                }

                field(Name; Rec.Name)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer name.';
                    ShowMandatory = true;
                }

                field("Search Name"; Rec."Search Name")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the search name.';
                    Visible = false;
                }

                field("Customer Type"; Rec."Customer Type")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the type of customer.';
                }

                field(Blocked; Rec.Blocked)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies if the customer is blocked.';
                }

                field("Last Date Modified"; Rec."Last Date Modified")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies when the customer was last modified.';
                    Editable = false;
                }
            }

            group(AddressAndContact)
            {
                Caption = 'Address & Contact';

                field(Address; Rec.Address)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer address.';
                }

                field("Address 2"; Rec."Address 2")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies additional address information.';
                }

                field(City; Rec.City)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the city.';
                }

                field("Phone No."; Rec."Phone No.")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the phone number.';
                }

                field("E-Mail"; Rec."E-Mail")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the email address.';
                    ExtendedDatatype = EMail;
                }
            }

            group(Invoicing)
            {
                Caption = 'Invoicing';

                field("Credit Limit"; Rec."Credit Limit")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the credit limit.';
                }

                field(Balance; Rec.Balance)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer balance.';
                    DrillDownPageId = "Customer Ledger Entries";
                }

                field("Payment Terms Code"; Rec."Payment Terms Code")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the payment terms.';
                }

                field("Currency Code"; Rec."Currency Code")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the currency code.';
                }
            }
        }

        area(FactBoxes)
        {
            part(CustomerPicture; "Customer Picture")
            {
                ApplicationArea = All;
                SubPageLink = "No." = field("No.");
            }

            systempart(Links; Links)
            {
                ApplicationArea = RecordLinks;
            }

            systempart(Notes; Notes)
            {
                ApplicationArea = Notes;
            }
        }
    }

    actions
    {
        area(Navigation)
        {
            group(Customer)
            {
                Caption = '&Customer';

                action(LedgerEntries)
                {
                    ApplicationArea = All;
                    Caption = 'Ledger E&ntries';
                    Image = CustomerLedger;
                    RunObject = page "Customer Ledger Entries";
                    RunPageLink = "Customer No." = field("No.");
                    RunPageView = sorting("Customer No.");
                    ShortcutKey = 'Ctrl+F7';
                    ToolTip = 'View the history of transactions for the customer.';
                }

                action(Statistics)
                {
                    ApplicationArea = All;
                    Caption = 'Statistics';
                    Image = Statistics;
                    RunObject = page "Customer Statistics";
                    RunPageLink = "No." = field("No.");
                    ShortcutKey = 'F7';
                    ToolTip = 'View statistical information about the customer.';
                }
            }
        }

        area(Processing)
        {
            group(Functions)
            {
                Caption = 'F&unctions';

                action(CheckCreditLimit)
                {
                    ApplicationArea = All;
                    Caption = 'Check Credit Limit';
                    Image = Check;
                    ToolTip = 'Check if the customer has exceeded their credit limit.';

                    trigger OnAction()
                    begin
                        Rec.CheckCreditLimit();
                    end;
                }

                action(ProcessPayment)
                {
                    ApplicationArea = All;
                    Caption = 'Process Payment';
                    Image = Payment;
                    ToolTip = 'Process a payment for this customer.';

                    trigger OnAction()
                    var
                        PaymentProcessor: Interface IPaymentProcessor;
                    begin
                        PaymentProcessor := CustomerMgt.GetPaymentProcessor();
                        PaymentProcessor.ProcessPayment(Rec);
                    end;
                }
            }
        }

        area(Promoted)
        {
            group(Category_Process)
            {
                Caption = 'Process';

                actionref(CheckCreditLimit_Promoted; CheckCreditLimit)
                {
                }

                actionref(ProcessPayment_Promoted; ProcessPayment)
                {
                }
            }

            group(Category_Customer)
            {
                Caption = 'Customer';

                actionref(Statistics_Promoted; Statistics)
                {
                }

                actionref(LedgerEntries_Promoted; LedgerEntries)
                {
                }
            }
        }
    }

    var
        CustomerMgt: Codeunit CustomerMgt;

    trigger OnOpenPage()
    begin
        Rec.SetRange("Customer Type");
    end;

    trigger OnAfterGetRecord()
    begin
        CheckCreditStatus();
    end;

    local procedure CheckCreditStatus()
    begin
        if Rec."Credit Limit" = 0 then
            exit;

        Rec.CalcFields(Balance);
        if Rec.Balance > Rec."Credit Limit" then
            Message('Warning: Customer has exceeded credit limit');
    end;
}