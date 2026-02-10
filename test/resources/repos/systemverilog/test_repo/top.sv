// Top module that instantiates counter and alu for cross-file testing
`include "types.svh"

module top (
    input  logic        clk,
    input  logic        rst_n,
    input  logic        enable,
    input  word_t       a,
    input  word_t       b,
    input  logic [2:0]  op,
    output byte_t       count,
    output word_t       alu_result,
    output logic        alu_zero
);

    // Instantiate counter module
    counter #(.WIDTH(8)) u_counter (
        .clk(clk),
        .rst_n(rst_n),
        .enable(enable),
        .count(count)
    );

    // Instantiate ALU module
    alu #(.DATA_WIDTH(32)) u_alu (
        .a(a),
        .b(b),
        .op(op),
        .result(alu_result),
        .zero(alu_zero)
    );

endmodule
