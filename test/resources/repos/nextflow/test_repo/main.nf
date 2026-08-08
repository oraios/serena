#!/usr/bin/env nextflow

include { GREET; SHOUT } from './modules/greet/main.nf'
include { buildGreeting } from './modules/util/main.nf'

params.names = ['Ada', 'Grace']

workflow SAY_HELLO {
    take:
    names

    main:
    greetings = GREET(names)
    shouted = SHOUT(greetings)

    emit:
    shouted
}

workflow {
    log.info buildGreeting('World')
    SAY_HELLO(Channel.fromList(params.names))
}
