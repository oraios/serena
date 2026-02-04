// Common types header for testing SystemVerilog LSP
`ifndef TYPES_SVH
`define TYPES_SVH

typedef logic [7:0] byte_t;
typedef logic [15:0] halfword_t;
typedef logic [31:0] word_t;
typedef logic [63:0] doubleword_t;

typedef struct packed {
    logic valid;
    logic [31:0] data;
    logic [3:0] tag;
} tagged_data_t;

`endif // TYPES_SVH
