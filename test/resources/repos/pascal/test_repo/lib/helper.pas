unit Helper;

{$mode objfpc}{$H+}

interface

uses
  Classes, SysUtils;

type
  { THelper - A helper class with utility functions }
  THelper = class
  public
    class function FormatString(const Template: string; const Args: array of const): string;
    class function IsEven(Number: Integer): Boolean;
  end;

{ Standalone helper functions }
function GetHelperMessage: string;
function MultiplyNumbers(A, B: Integer): Integer;
procedure LogMessage(const Msg: string);

implementation

{ THelper }

class function THelper.FormatString(const Template: string; const Args: array of const): string;
begin
  Result := Format(Template, Args);
end;

class function THelper.IsEven(Number: Integer): Boolean;
begin
  Result := (Number mod 2) = 0;
end;

{ Standalone functions }

function GetHelperMessage: string;
begin
  Result := 'Hello from Helper unit!';
end;

function MultiplyNumbers(A, B: Integer): Integer;
begin
  Result := A * B;
end;

procedure LogMessage(const Msg: string);
begin
  WriteLn('[LOG] ', Msg);
end;

end.
