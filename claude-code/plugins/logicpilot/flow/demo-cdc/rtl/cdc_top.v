// Two-clock-domain top wraps async_fifo with simple producer + consumer.
//
// LogicPilot top module — `top_module = "cdc_top"` in the CDC inventory.

`default_nettype none

module cdc_top (
    input  wire       wr_clk,
    input  wire       wr_rst_n,
    input  wire       rd_clk,
    input  wire       rd_rst_n,
    input  wire       wr_en,
    input  wire [7:0] wr_data,
    input  wire       rd_en,
    output wire [7:0] rd_data,
    output wire       full,
    output wire       empty
);
    async_fifo #(.DEPTH(8), .WIDTH(8)) u_fifo (
        .wr_clk    (wr_clk),
        .wr_rst_n  (wr_rst_n),
        .wr_en     (wr_en),
        .wr_data   (wr_data),
        .full      (full),
        .rd_clk    (rd_clk),
        .rd_rst_n  (rd_rst_n),
        .rd_en     (rd_en),
        .rd_data   (rd_data),
        .empty     (empty)
    );
endmodule

`default_nettype wire
