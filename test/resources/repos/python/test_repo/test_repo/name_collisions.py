# ruff: noqa
var_will_be_overwritten = 1

var_will_be_overwritten = 2


def func_using_overwritten_var():
    print(var_will_be_overwritten)


class ClassWillBeOverwritten:
    def method1(self):
        pass


class ClassWillBeOverwritten:
    def method2(self):
        pass


def func_will_be_overwritten():
    pass


def func_will_be_overwritten():
    pass


def func_calling_overwritten_func():
    func_will_be_overwritten()


def func_calling_overwritten_class():
    ClassWillBeOverwritten()
