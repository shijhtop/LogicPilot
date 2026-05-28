`timescale 1ns/1ps
module counter_tb;
    reg clk = 0, rst_n = 0, en = 0;
    wire [7:0] count;

    counter #(.WIDTH(8)) dut (.clk(clk), .rst_n(rst_n), .en(en), .count(count));

    always #5 clk = ~clk;   // 100 MHz

    initial begin
        $dumpfile("build/wave.vcd");
        $dumpvars(0, counter_tb);
        #12 rst_n = 1; en = 1;
        #100;
        if (count == 8'd0) begin $display("FAIL: counter did not advance"); $fatal; end
        $display("PASS: count=%0d", count);
        $finish;
    end
endmodule
