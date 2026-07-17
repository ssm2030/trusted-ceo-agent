"use client";

import { BarChart, GraphChart, LineChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import {
  init,
  use as registerEChartsModules,
  type EChartsCoreOption,
  type EChartsType,
} from "echarts/core";
import { SVGRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";

import styles from "@/features/report/ReportWorkspace.module.css";

registerEChartsModules([
  BarChart,
  GraphChart,
  GridComponent,
  LegendComponent,
  LineChart,
  SVGRenderer,
  TooltipComponent,
]);

export type CanvasBinding = {
  dataIndex: number;
  ref: string;
};

type EChartCanvasProps = {
  ariaLabel: string;
  bindings: CanvasBinding[];
  onBindingSelect: (ref: string) => void;
  option: EChartsCoreOption;
};

export function EChartCanvas({
  ariaLabel,
  bindings,
  onBindingSelect,
  option,
}: EChartCanvasProps) {
  const hostRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (host === null) {
      return;
    }

    const chart: EChartsType = init(host, undefined, { renderer: "svg" });
    chart.setOption(option, { notMerge: true });

    const handleClick = (params: { dataIndex?: number }) => {
      if (typeof params.dataIndex !== "number") {
        return;
      }
      const binding = bindings.find(
        (candidate) => candidate.dataIndex === params.dataIndex,
      );
      if (binding !== undefined) {
        onBindingSelect(binding.ref);
      }
    };
    chart.on("click", handleClick);

    const resizeObserver =
      typeof ResizeObserver === "undefined"
        ? null
        : new ResizeObserver(() => chart.resize());
    resizeObserver?.observe(host);

    return () => {
      resizeObserver?.disconnect();
      chart.off("click", handleClick);
      chart.dispose();
    };
  }, [bindings, onBindingSelect, option]);

  return (
    <div
      aria-label={ariaLabel}
      className={styles.chartCanvas}
      ref={hostRef}
      role="img"
    />
  );
}
