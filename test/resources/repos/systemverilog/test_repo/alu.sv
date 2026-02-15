// ALU module for testing SystemVerilog LSP
module alu #(
    parameter DATA_WIDTH = 32
) (
    input  logic [DATA_WIDTH-1:0] a,
    input  logic [DATA_WIDTH-1:0] b,
    input  logic [2:0] op,
    output logic [DATA_WIDTH-1:0] result,
    output logic zero
);

    typedef enum logic [2:0] {
        ALU_ADD = 3'b000,
        ALU_SUB = 3'b001,
        ALU_AND = 3'b010,
        ALU_OR  = 3'b011,
        ALU_XOR = 3'b100,
        ALU_SLL = 3'b101,
        ALU_SRL = 3'b110,
        ALU_SRA = 3'b111
    } alu_op_t;

    always_comb begin
        case (op)
            ALU_ADD: result = a + b;
            ALU_SUB: result = a - b;
            ALU_AND: result = a & b;
            ALU_OR:  result = a | b;
            ALU_XOR: result = a ^ b;
            ALU_SLL: result = a << b[4:0];
            ALU_SRL: result = a >> b[4:0];
            ALU_SRA: result = $signed(a) >>> b[4:0];
            default: result = '0;
        endcase
    end

    assign zero = (result == '0);

endmodule
