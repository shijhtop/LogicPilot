// Two-stage synchronizer for level signals crossing clock domains.
//
// Standard CDC primitive. Both flops on the destination clock; the
// LogicPilot CDC inventory should list this as payload_kind="level",
// synchronizer="2ff", stages=2.

`default_nettype none

module sync_2ff #(
    parameter WIDTH = 1
) (
    input  wire             dst_clk,
    input  wire             dst_rst_n,
    input  wire [WIDTH-1:0] src_d,
    output wire [WIDTH-1:0] dst_q
);
    reg [WIDTH-1:0] q1, q2;

    always @(posedge dst_clk or negedge dst_rst_n) begin
        if (!dst_rst_n) begin
            q1 <= {WIDTH{1'b0}};
            q2 <= {WIDTH{1'b0}};
        end else begin
            q1 <= src_d;
            q2 <= q1;
        end
    end

    assign dst_q = q2;
endmodule

`default_nettype wire
