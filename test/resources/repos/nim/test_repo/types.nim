# Type definitions module

import std/[strformat, tables, options, math]

type
  Point* = object
    x*, y*: float

  Rectangle* = object
    topLeft*: Point
    width*, height*: float

  Shape* = ref object of RootObj
    color*: string

  Circle* = ref object of Shape
    center*: Point
    radius*: float

  Triangle* = ref object of Shape
    a*, b*, c*: Point

  Color* = enum
    Red = "red"
    Green = "green"
    Blue = "blue"
    Yellow = "yellow"
    Purple = "purple"

  Status* = enum
    Pending
    InProgress
    Completed
    Failed

  Result*[T, E] = object
    case kind*: bool
    of true:
      value*: T
    of false:
      error*: E

proc newPoint*(x, y: float): Point =
  ## Creates a new Point
  Point(x: x, y: y)

proc toString*(p: Point): string =
  ## Converts a Point to string
  fmt"({p.x:.2f}, {p.y:.2f})"

proc distance*(p1, p2: Point): float =
  ## Calculates distance between two points
  let dx = p2.x - p1.x
  let dy = p2.y - p1.y
  sqrt(dx * dx + dy * dy)

proc newRectangle*(x, y, width, height: float): Rectangle =
  ## Creates a new Rectangle
  Rectangle(topLeft: newPoint(x, y), width: width, height: height)

proc area*(r: Rectangle): float =
  ## Calculates area of a rectangle
  r.width * r.height

proc perimeter*(r: Rectangle): float =
  ## Calculates perimeter of a rectangle
  2 * (r.width + r.height)

proc contains*(r: Rectangle, p: Point): bool =
  ## Checks if a point is inside the rectangle
  p.x >= r.topLeft.x and
  p.x <= r.topLeft.x + r.width and
  p.y >= r.topLeft.y and
  p.y <= r.topLeft.y + r.height

method draw*(s: Shape): string {.base.} =
  ## Base draw method for shapes
  "Drawing a shape with color: " & s.color

method draw*(c: Circle): string =
  ## Draw method for Circle
  fmt"Drawing a circle at {c.center.toString()} with radius {c.radius:.2f}"

method draw*(t: Triangle): string =
  ## Draw method for Triangle
  "Drawing a triangle with vertices at " &
  t.a.toString() & ", " & t.b.toString() & ", " & t.c.toString()

proc ok*[T, E](value: T): Result[T, E] =
  ## Creates a successful Result
  Result[T, E](kind: true, value: value)

proc err*[T, E](error: E): Result[T, E] =
  ## Creates an error Result
  Result[T, E](kind: false, error: error)

proc isOk*[T, E](r: Result[T, E]): bool =
  ## Checks if Result is successful
  r.kind

proc isErr*[T, E](r: Result[T, E]): bool =
  ## Checks if Result is an error
  not r.kind

type
  Database* = ref object
    data: Table[string, string]

proc newDatabase*(): Database =
  ## Creates a new Database
  Database(data: initTable[string, string]())

proc set*(db: Database, key, value: string) =
  ## Sets a value in the database
  db.data[key] = value

proc get*(db: Database, key: string): Option[string] =
  ## Gets a value from the database
  if key in db.data:
    some(db.data[key])
  else:
    none(string)

proc delete*(db: Database, key: string): bool =
  ## Deletes a key from the database
  if key in db.data:
    db.data.del(key)
    true
  else:
    false