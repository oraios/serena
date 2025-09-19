page 50002 "TEST Customer List"
{
    Caption = 'Customer List';
    PageType = List;
    ApplicationArea = All;
    UsageCategory = Lists;
    SourceTable = "TEST Customer";
    CardPageId = "TEST Customer Card";
    Editable = false;

    layout
    {
        area(Content)
        {
            repeater(Group)
            {
                field("No."; Rec."No.")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer number.';
                }

                field(Name; Rec.Name)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer name.';
                }

                field(City; Rec.City)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the city.';
                }

                field("Customer Type"; Rec."Customer Type")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the type of customer.';
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
                }

                field(Balance; Rec.Balance)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the customer balance.';
                    StyleExpr = BalanceStyleExpr;
                }

                field("Credit Limit"; Rec."Credit Limit")
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies the credit limit.';
                }

                field(Blocked; Rec.Blocked)
                {
                    ApplicationArea = All;
                    ToolTip = 'Specifies if the customer is blocked.';
                }
            }
        }

        area(FactBoxes)
        {
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
        area(Processing)
        {
            action(NewCustomer)
            {
                ApplicationArea = All;
                Caption = 'New';
                Image = NewCustomer;
                ToolTip = 'Create a new customer.';

                trigger OnAction()
                begin
                    CustomerMgt.CreateNewCustomer();
                end;
            }

            action(ExportToExcel)
            {
                ApplicationArea = All;
                Caption = 'Export to Excel';
                Image = ExportToExcel;
                ToolTip = 'Export the customer list to Excel.';

                trigger OnAction()
                begin
                    ExportCustomersToExcel();
                end;
            }
        }

        area(Navigation)
        {
            action(ViewStatistics)
            {
                ApplicationArea = All;
                Caption = 'Statistics';
                Image = Statistics;
                RunObject = page "Customer Statistics";
                RunPageLink = "No." = field("No.");
                ToolTip = 'View customer statistics.';
            }
        }

        area(Promoted)
        {
            group(Category_New)
            {
                Caption = 'New';

                actionref(NewCustomer_Promoted; NewCustomer)
                {
                }
            }

            group(Category_Process)
            {
                Caption = 'Process';

                actionref(ExportToExcel_Promoted; ExportToExcel)
                {
                }
            }
        }
    }

    trigger OnAfterGetRecord()
    begin
        SetBalanceStyle();
    end;

    var
        CustomerMgt: Codeunit CustomerMgt;
        BalanceStyleExpr: Text;

    local procedure SetBalanceStyle()
    begin
        BalanceStyleExpr := '';

        Rec.CalcFields(Balance);
        if (Rec."Credit Limit" <> 0) and (Rec.Balance > Rec."Credit Limit") then
            BalanceStyleExpr := 'Unfavorable';
    end;

    local procedure ExportCustomersToExcel()
    var
        ExcelBuffer: Record "Excel Buffer" temporary;
        RowNo: Integer;
    begin
        ExcelBuffer.Reset();
        ExcelBuffer.DeleteAll();

        // Add headers
        RowNo := 1;
        ExcelBuffer.AddColumn('Customer No.', false, '', false, false, false, '', ExcelBuffer."Cell Type"::Text);
        ExcelBuffer.AddColumn('Name', false, '', false, false, false, '', ExcelBuffer."Cell Type"::Text);
        ExcelBuffer.AddColumn('City', false, '', false, false, false, '', ExcelBuffer."Cell Type"::Text);
        ExcelBuffer.AddColumn('Balance', false, '', false, false, false, '', ExcelBuffer."Cell Type"::Number);
        ExcelBuffer.NewRow();

        // Add data
        if rec.FindSet() then
            repeat
                RowNo += 1;
                rec.CalcFields(Balance);
                ExcelBuffer.AddColumn(rec."No.", false, '', false, false, false, '', ExcelBuffer."Cell Type"::Text);
                ExcelBuffer.AddColumn(rec.Name, false, '', false, false, false, '', ExcelBuffer."Cell Type"::Text);
                ExcelBuffer.AddColumn(rec.City, false, '', false, false, false, '', ExcelBuffer."Cell Type"::Text);
                ExcelBuffer.AddColumn(rec.Balance, false, '', false, false, false, '', ExcelBuffer."Cell Type"::Number);
                ExcelBuffer.NewRow();
            until rec.Next() = 0;

        ExcelBuffer.CreateNewBook('Customers');
        ExcelBuffer.WriteSheet('Customer List', CompanyName, UserId);
        ExcelBuffer.CloseBook();
        ExcelBuffer.OpenExcel();
    end;
}