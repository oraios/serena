table 50000 "TEST Customer"
{
    Caption = 'Customer';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "No."; Code[20])
        {
            Caption = 'No.';
            DataClassification = CustomerContent;

            trigger OnValidate()
            begin
                if "No." <> xRec."No." then begin
                    CustomerMgt.TestNoSeries();
                    "No. Series" := '';
                end;
            end;
        }

        field(2; Name; Text[100])
        {
            Caption = 'Name';
            DataClassification = CustomerContent;

            trigger OnValidate()
            begin
                if Name <> xRec.Name then
                    UpdateSearchName();
            end;
        }

        field(3; "Search Name"; Code[100])
        {
            Caption = 'Search Name';
            DataClassification = CustomerContent;
        }

        field(4; Address; Text[100])
        {
            Caption = 'Address';
            DataClassification = CustomerContent;
        }

        field(5; "Address 2"; Text[50])
        {
            Caption = 'Address 2';
            DataClassification = CustomerContent;
        }

        field(6; City; Text[30])
        {
            Caption = 'City';
            DataClassification = CustomerContent;
        }

        field(7; "Phone No."; Text[30])
        {
            Caption = 'Phone No.';
            DataClassification = CustomerContent;
        }

        field(8; "E-Mail"; Text[80])
        {
            Caption = 'E-Mail';
            DataClassification = CustomerContent;

            trigger OnValidate()
            var
                MailMgt: Codeunit "Mail Management";
            begin
                MailMgt.CheckValidEmailAddresses("E-Mail");
            end;
        }

        field(10; "Customer Type"; Enum CustomerType)
        {
            Caption = 'Customer Type';
            DataClassification = CustomerContent;
        }

        field(11; Balance; Decimal)
        {
            Caption = 'Balance';
            Editable = false;
            FieldClass = FlowField;
            CalcFormula = sum("Cust. Ledger Entry".Amount where("Customer No." = field("No.")));
        }

        field(12; "Credit Limit"; Decimal)
        {
            Caption = 'Credit Limit';
            DataClassification = CustomerContent;
        }

        field(13; Blocked; Boolean)
        {
            Caption = 'Blocked';
            DataClassification = CustomerContent;
        }

        field(14; "Last Date Modified"; Date)
        {
            Caption = 'Last Date Modified';
            DataClassification = CustomerContent;
            Editable = false;
        }

        field(15; "No. Series"; Code[20])
        {
            Caption = 'No. Series';
            DataClassification = CustomerContent;
        }

        field(20; "Payment Terms Code"; Code[10])
        {
            Caption = 'Payment Terms Code';
            DataClassification = CustomerContent;
            TableRelation = "Payment Terms";
        }

        field(21; "Currency Code"; Code[10])
        {
            Caption = 'Currency Code';
            DataClassification = CustomerContent;
            TableRelation = Currency;
        }
    }

    keys
    {
        key(PK; "No.")
        {
            Clustered = true;
        }

        key(SearchName; "Search Name")
        {
        }

        key(CustomerType; "Customer Type", City)
        {
        }
    }

    fieldgroups
    {
        fieldgroup(DropDown; "No.", Name, City)
        {
        }

        fieldgroup(Brick; "No.", Name, Balance)
        {
        }
    }

    trigger OnInsert()
    begin
        if "No." = '' then begin
            CustomerMgt.TestNoSeries();
            CustomerMgt.InitNo(Rec);
        end;

        "Last Date Modified" := Today();
    end;

    trigger OnModify()
    begin
        "Last Date Modified" := Today();
    end;

    trigger OnDelete()
    var
        CustomerLedgerEntry: Record "Cust. Ledger Entry";
    begin
        CustomerLedgerEntry.SetRange("Customer No.", "No.");
        if not CustomerLedgerEntry.IsEmpty() then
            Error('Cannot delete customer %1 with ledger entries', "No.");
    end;

    trigger OnRename()
    begin
        "Last Date Modified" := Today();
    end;

    var
        CustomerMgt: Codeunit CustomerMgt;

    procedure UpdateSearchName()
    begin
        "Search Name" := UpperCase(Name);
    end;

    procedure CheckCreditLimit()
    var
        CreditLimitExceeded: Boolean;
    begin
        CalcFields(Balance);
        CreditLimitExceeded := (Balance > "Credit Limit") and ("Credit Limit" <> 0);

        if CreditLimitExceeded then
            Message('Credit limit exceeded for customer %1', "No.");
    end;

    procedure GetDisplayName(): Text
    begin
        exit(Name + ' (' + "No." + ')');
    end;
}