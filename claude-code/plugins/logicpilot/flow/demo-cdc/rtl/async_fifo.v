// Small asynchronous FIFO (gray-coded pointers across two clock domains).
//
// Cummings-style design: gray-coded read and write pointers cross the
// domain boundary, with binary equivalents kept local for arithmetic.
// Depth fixed at 8 for the demo (DEPTH must be power of 2).
//
// LogicPilot exercise points:
//   - Two distinct clock domains (wr_clk, rd_clk)
//   - Two legitimate CDC crossings (wr_ptr_gray → rd_clk; rd_ptr_gray → wr_clk)
//   - Both use payload_kind="bus", synchronizer="gray_counter"
//   - Documented in docs/cdc-inventory.json

`default_nettype none

module async_fifo #(
    parameter DEPTH = 8,            // must be power of 2
    parameter WIDTH = 8
) (
    // write domain
    input  wire             wr_clk,
    input  wire             wr_rst_n,
    input  wire             wr_en,
    input  wire [WIDTH-1:0] wr_data,
    output wire             full,
    // read domain
    input  wire             rd_clk,
    input  wire             rd_rst_n,
    input  wire             rd_en,
    output wire [WIDTH-1:0] rd_data,
    output wire             empty
);
    localparam AW = $clog2(DEPTH);

    // memory shared between domains (only ever READ-then-WRITE pattern
    // each cycle; pointer logic guards racing)
    reg [WIDTH-1:0] mem [0:DEPTH-1];

    // --- write side ----------------------------------------------------
    reg  [AW:0] wr_ptr_bin;       // one extra bit for full/empty detect
    reg  [AW:0] wr_ptr_gray;
    wire [AW:0] wr_ptr_bin_next  = wr_ptr_bin + (wr_en & ~full);
    wire [AW:0] wr_ptr_gray_next = (wr_ptr_bin_next >> 1) ^ wr_ptr_bin_next;

    always @(posedge wr_clk or negedge wr_rst_n) begin
        if (!wr_rst_n) begin
            wr_ptr_bin  <= {(AW+1){1'b0}};
            wr_ptr_gray <= {(AW+1){1'b0}};
        end else begin
            wr_ptr_bin  <= wr_ptr_bin_next;
            wr_ptr_gray <= wr_ptr_gray_next;
        end
    end

    always @(posedge wr_clk) begin
        if (wr_en & ~full) mem[wr_ptr_bin[AW-1:0]] <= wr_data;
    end

    // --- read side -----------------------------------------------------
    reg  [AW:0] rd_ptr_bin;
    reg  [AW:0] rd_ptr_gray;
    wire [AW:0] rd_ptr_bin_next  = rd_ptr_bin + (rd_en & ~empty);
    wire [AW:0] rd_ptr_gray_next = (rd_ptr_bin_next >> 1) ^ rd_ptr_bin_next;

    always @(posedge rd_clk or negedge rd_rst_n) begin
        if (!rd_rst_n) begin
            rd_ptr_bin  <= {(AW+1){1'b0}};
            rd_ptr_gray <= {(AW+1){1'b0}};
        end else begin
            rd_ptr_bin  <= rd_ptr_bin_next;
            rd_ptr_gray <= rd_ptr_gray_next;
        end
    end

    assign rd_data = mem[rd_ptr_bin[AW-1:0]];

    // --- CDC: synchronize each gray pointer into the OTHER domain ------
    wire [AW:0] wr_ptr_gray_in_rd_clk;
    wire [AW:0] rd_ptr_gray_in_wr_clk;

    sync_2ff #(.WIDTH(AW+1)) u_sync_wr2rd (
        .dst_clk   (rd_clk),
        .dst_rst_n (rd_rst_n),
        .src_d     (wr_ptr_gray),
        .dst_q     (wr_ptr_gray_in_rd_clk)
    );

    sync_2ff #(.WIDTH(AW+1)) u_sync_rd2wr (
        .dst_clk   (wr_clk),
        .dst_rst_n (wr_rst_n),
        .src_d     (rd_ptr_gray),
        .dst_q     (rd_ptr_gray_in_wr_clk)
    );

    // empty: read pointer caught up to synced write pointer
    assign empty = (rd_ptr_gray == wr_ptr_gray_in_rd_clk);

    // full: write pointer is one lap ahead of synced read pointer
    // (gray-coded check: top two bits inverted, lower bits equal)
    assign full  = (wr_ptr_gray[AW:AW-1] == ~rd_ptr_gray_in_wr_clk[AW:AW-1]) &&
                   (wr_ptr_gray[AW-2:0]  ==  rd_ptr_gray_in_wr_clk[AW-2:0]);

endmodule

`default_nettype wire
