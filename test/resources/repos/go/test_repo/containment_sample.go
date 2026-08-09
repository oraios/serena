package main

type Severity int

const (
    SevLow Severity = iota
    SevHigh
)

type Alert struct {
    Level Severity
    Msg   string
}

func (a Alert) IsHigh() bool {
    return a.Level == SevHigh
}

type Notifier interface {
    Notify(level Severity) error
}
