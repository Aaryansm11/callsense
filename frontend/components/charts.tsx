"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  PolarAngleAxis,
  PolarGrid,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const AXIS = { fontSize: 11, fill: "#6b7280" };

export function TrendLine({
  data,
}: {
  data: { label: string; value: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="label" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis domain={[0, 100]} tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
        <Line
          type="monotone"
          dataKey="value"
          stroke="#4f46e5"
          strokeWidth={2}
          dot={{ r: 3 }}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function TeamBars({
  data,
}: {
  data: { name: string; value: number }[];
}) {
  const color = (v: number) =>
    v >= 70 ? "#16a34a" : v >= 40 ? "#d97706" : "#dc2626";
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ top: 8, right: 12, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
        <XAxis dataKey="name" tick={AXIS} tickLine={false} axisLine={false} />
        <YAxis domain={[0, 100]} tick={AXIS} tickLine={false} axisLine={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} cursor={{ fill: "#f9fafb" }} />
        <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive={false}>
          {data.map((d, i) => (
            <Cell key={i} fill={color(d.value)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

export function DimensionRadar({
  data,
}: {
  data: { dimension: string; my: number; team: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={280}>
      <RadarChart data={data} outerRadius="72%">
        <PolarGrid stroke="#e5e7eb" />
        <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 10, fill: "#6b7280" }} />
        <Radar name="Team avg" dataKey="team" stroke="#9ca3af" fill="#9ca3af" fillOpacity={0.15} isAnimationActive={false} />
        <Radar name="Advisor" dataKey="my" stroke="#4f46e5" fill="#4f46e5" fillOpacity={0.35} isAnimationActive={false} />
        <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
