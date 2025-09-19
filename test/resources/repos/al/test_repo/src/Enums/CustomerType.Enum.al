enum 50000 CustomerType
{
    Extensible = true;
    Caption = 'Customer Type';
    
    value(0; "")
    {
        Caption = '';
    }
    
    value(1; Regular)
    {
        Caption = 'Regular';
    }
    
    value(2; Premium)
    {
        Caption = 'Premium';
    }
    
    value(3; VIP)
    {
        Caption = 'VIP';
    }
    
    value(4; Corporate)
    {
        Caption = 'Corporate';
    }
    
    value(5; Government)
    {
        Caption = 'Government';
    }
}