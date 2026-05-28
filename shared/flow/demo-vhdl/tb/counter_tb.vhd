library ieee;
use ieee.std_logic_1164.all;
use ieee.numeric_std.all;

entity counter_tb is end entity;

architecture sim of counter_tb is
  signal clk   : std_logic := '0';
  signal rst_n : std_logic := '0';
  signal en    : std_logic := '0';
  signal count : std_logic_vector(7 downto 0);
begin
  dut : entity work.counter
    generic map (WIDTH => 8)
    port map (clk => clk, rst_n => rst_n, en => en, count => count);

  clk <= not clk after 5 ns;  -- 100 MHz

  process
  begin
    wait for 12 ns; rst_n <= '1'; en <= '1';
    wait for 100 ns;
    assert unsigned(count) /= 0 report "FAIL: counter did not advance" severity failure;
    report "PASS: count=" & integer'image(to_integer(unsigned(count)));
    std.env.finish;
  end process;
end architecture;
