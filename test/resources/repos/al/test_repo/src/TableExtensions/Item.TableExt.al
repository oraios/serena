tableextension 50000 ItemExt extends Item
{
    fields
    {
        field(50000; "Customer No."; Code[20])
        {
            Caption = 'Preferred Customer No.';
            DataClassification = CustomerContent;
            TableRelation = "TEST Customer";

            trigger OnValidate()
            var
                Customer: Record "TEST Customer";
            begin
                if "Customer No." <> '' then begin
                    Customer.Get("Customer No.");
                    "Customer Name" := Customer.Name;
                end else
                    "Customer Name" := '';
            end;
        }

        field(50001; "Customer Name"; Text[100])
        {
            Caption = 'Preferred Customer Name';
            DataClassification = CustomerContent;
            Editable = false;
        }

        field(50002; "Special Discount %"; Decimal)
        {
            Caption = 'Special Discount %';
            DataClassification = CustomerContent;
            MinValue = 0;
            MaxValue = 100;
        }

        field(50003; "Last Sale Date"; Date)
        {
            Caption = 'Last Sale Date';
            DataClassification = CustomerContent;
            Editable = false;
        }

        field(50004; "Total Sales Qty"; Decimal)
        {
            Caption = 'Total Sales Quantity';
            FieldClass = FlowField;
            CalcFormula = sum("Sales Line".Quantity where("No." = field("No."),
                                                           Type = const(Item)));
            Editable = false;
        }
    }

    keys
    {
        key(CustomerKey; "Customer No.")
        {
        }
    }

    procedure UpdateLastSaleDate()
    begin
        "Last Sale Date" := Today();
        Modify();
    end;

    procedure GetSpecialPrice(Customer: Record "TEST Customer"): Decimal
    var
        BasePrice: Decimal;
    begin
        BasePrice := "Unit Price";

        if "Customer No." = Customer."No." then
            BasePrice := BasePrice * (1 - "Special Discount %" / 100);

        exit(BasePrice);
    end;
}