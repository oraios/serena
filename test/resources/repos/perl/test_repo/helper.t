#!/usr/bin/env perl

use lib '.';
use strict;
use warnings;

use Test::More tests => 1;

require helper;

helper_function();
ok(1, 'helper_function callable from .t file');
