; Utility aliases and handlers

alias format.coins {
  return $bytes($1,b) doubloons
}

alias is.admin {
  if ($1 isop $chan) return $true
  return $false
}

alias welcome.message {
  greet $1
  msg $chan You have $format.coins(100) to start with!
}

dialog settings {
  title "Game Settings"
  size -1 -1 200 150
  edit "", 1, 10 10 180 20
  button "Save", 2, 60 40 80 25
}

ctcp *:VERSION:*: {
  ctcpreply $nick VERSION PiratesIRC v1.0
}
