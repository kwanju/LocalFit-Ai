// react-activity-calendar wrapper (ADR-020).
// Maps DayStat[] → Activity[]. Click opens DayDetailModal via renderBlock.

import React, { useState } from "react";
import { ActivityCalendar, type Activity } from "react-activity-calendar";
import type { DayStat } from "@/api/calendar";
import { DayDetailModal } from "./DayDetailModal";

interface Props {
  data: DayStat[];
  year: number;
}

// Dark theme: slate-900 → green gradient (level 0-4)
const THEME = {
  dark: ["#1e293b", "#166534", "#15803d", "#16a34a", "#22c55e"],
  light: ["#e2e8f0", "#bbf7d0", "#86efac", "#4ade80", "#22c55e"],
};

function buildActivities(stats: DayStat[], year: number): Activity[] {
  const yearStr = String(year);
  const dateSet = new Set(stats.map((s) => s.date));
  const activities: Activity[] = [];

  // Anchor entries so the library renders the full year grid
  if (!dateSet.has(`${yearStr}-01-01`))
    activities.push({ date: `${yearStr}-01-01`, count: 0, level: 0 });
  if (!dateSet.has(`${yearStr}-12-31`))
    activities.push({ date: `${yearStr}-12-31`, count: 0, level: 0 });

  for (const stat of stats) {
    if (!stat.date.startsWith(yearStr)) continue;
    activities.push({
      date: stat.date,
      count: Math.round(stat.volume),
      level: stat.level as 0 | 1 | 2 | 3 | 4,
    });
  }

  return activities.sort((a, b) => a.date.localeCompare(b.date));
}

function tooltipText(stat: DayStat): string {
  const parts: string[] = [];
  if (stat.exercises.length > 0) parts.push(stat.exercises.join(" + "));
  if (stat.condition_avg != null) parts.push(`컨디션 ${stat.condition_avg.toFixed(0)}/10`);
  return parts.join(", ") || "운동 기록";
}

export function CalendarHeatmap({ data, year }: Props) {
  const [selected, setSelected] = useState<DayStat | null>(null);
  const byDate = new Map<string, DayStat>(data.map((s) => [s.date, s]));

  const activities = buildActivities(data, year);

  const renderBlock = (block: React.ReactElement, activity: Activity): React.ReactElement => {
    const stat = byDate.get(activity.date);
    const extraProps: Record<string, unknown> = {};

    if (stat?.sessions.length) {
      extraProps.onClick = () => setSelected(stat);
      extraProps.style = { cursor: "pointer" };
      extraProps.title = tooltipText(stat);
    }

    return React.cloneElement(block, extraProps);
  };

  return (
    <>
      <div className="overflow-x-auto rounded-xl bg-slate-900 p-4">
        <ActivityCalendar
          data={activities}
          theme={THEME}
          colorScheme="dark"
          labels={{
            months: [
              "1월","2월","3월","4월","5월","6월",
              "7월","8월","9월","10월","11월","12월",
            ],
            weekdays: ["일", "월", "화", "수", "목", "금", "토"],
            totalCount: `{{count}}회 운동 (${year}년)`,
            legend: { less: "적음", more: "많음" },
          }}
          showWeekdayLabels
          renderBlock={renderBlock}
        />
      </div>

      {selected && (
        <DayDetailModal stat={selected} onClose={() => setSelected(null)} />
      )}
    </>
  );
}
