; Main game module - tests alias, event, and menu parsing

alias greet {
  msg $chan Hello, $1 $+ ! Welcome aboard.
}

alias -l calculate.doubloons {
  var %base = 100
  var %bonus = $rand(1,50)
  return $calc(%base + %bonus)
}

on *:TEXT:!hello*:#: {
  greet $nick
}

on *:JOIN:#: {
  .timer 1 3 greet $nick
  var %coins = $format.coins(100)
  msg $chan You have %coins
}

raw 319:*: {
  ; Handle channel list numeric
  echo -a Channels: $3-
}

menu channel {
  Pirates Game
  .Start Game:/start
  .End Game:/stop
}

alias show.player.info {
  if ($is.admin($nick)) {
    msg $chan $nick is an admin with $format.coins(500)
  }
}
