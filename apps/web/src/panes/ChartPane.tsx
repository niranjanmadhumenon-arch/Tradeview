import { ticker } from "../format";
import { useStore } from "../state/store";
import { Empty } from "../ui";

/** TradingView's free embed carries BSE but not NSE data, so charts use the BSE listing. */
function tvSymbol(symbol: string): string {
  return `BSE:${ticker(symbol)}`;
}

export function ChartPane() {
  const selected = useStore((s) => s.selected);
  if (!selected) return <Empty title="No symbol selected" hint="Pick a holding or search a ticker in the ribbon." />;
  const params = new URLSearchParams({
    symbol: tvSymbol(selected),
    interval: "D",
    theme: "dark",
    style: "1",
    timezone: "Asia/Kolkata",
    locale: "en",
    withdateranges: "1",
    hide_side_toolbar: "0",
    allow_symbol_change: "1",
    save_image: "0",
    toolbar_bg: "#0d0f13",
  });
  return (
    <iframe
      key={selected}
      title={`${ticker(selected)} chart`}
      src={`https://s.tradingview.com/widgetembed/?${params}`}
      className="h-full w-full border-0"
      sandbox="allow-scripts allow-same-origin allow-popups"
      referrerPolicy="no-referrer"
    />
  );
}
