#!/usr/bin/env perl
use strict;
use warnings;
use lib '.';

require helper;

sub greet {
    my ($name) = @_;
    return "Hello, $name!";
}

my $user_name = "Perl User";
my $greeting = greet($user_name);

print "$greeting\n";

helper_function();

sub use_helper_function {
    helper_function();
}
