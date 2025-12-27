unit Main;

{$mode objfpc}{$H+}

interface

uses
  Classes, SysUtils, Helper;

type
  { TUser - A simple user class }
  TUser = class
  private
    FName: string;
    FAge: Integer;
  public
    constructor Create(const AName: string; AAge: Integer);
    destructor Destroy; override;

    function GetInfo: string;
    procedure UpdateAge(NewAge: Integer);

    property Name: string read FName write FName;
    property Age: Integer read FAge write FAge;
  end;

  { TUserManager - Manages multiple users }
  TUserManager = class
  private
    FUsers: TList;
  public
    constructor Create;
    destructor Destroy; override;

    procedure AddUser(User: TUser);
    function GetUserCount: Integer;
    function FindUserByName(const AName: string): TUser;
  end;

{ Helper functions }

/// Calculates the sum of two integers.
/// @param A First integer value
/// @param B Second integer value
/// @returns The sum of A and B
function CalculateSum(A, B: Integer): Integer;
procedure PrintMessage(const Msg: string);

implementation

{ TUser implementation }

constructor TUser.Create(const AName: string; AAge: Integer);
begin
  inherited Create;
  FName := AName;
  FAge := AAge;
end;

destructor TUser.Destroy;
begin
  inherited Destroy;
end;

function TUser.GetInfo: string;
begin
  Result := Format('Name: %s, Age: %d', [FName, FAge]);
end;

procedure TUser.UpdateAge(NewAge: Integer);
begin
  FAge := NewAge;
end;

{ TUserManager implementation }

constructor TUserManager.Create;
begin
  inherited Create;
  FUsers := TList.Create;
end;

destructor TUserManager.Destroy;
var
  i: Integer;
begin
  for i := 0 to FUsers.Count - 1 do
    TUser(FUsers[i]).Free;
  FUsers.Free;
  inherited Destroy;
end;

procedure TUserManager.AddUser(User: TUser);
begin
  FUsers.Add(User);
end;

function TUserManager.GetUserCount: Integer;
begin
  Result := FUsers.Count;
end;

function TUserManager.FindUserByName(const AName: string): TUser;
var
  i: Integer;
begin
  Result := nil;
  for i := 0 to FUsers.Count - 1 do
  begin
    if TUser(FUsers[i]).Name = AName then
    begin
      Result := TUser(FUsers[i]);
      Exit;
    end;
  end;
end;

{ Helper functions }

function CalculateSum(A, B: Integer): Integer;
begin
  Result := A + B;
end;

procedure PrintMessage(const Msg: string);
begin
  WriteLn(Msg);
end;

end.
