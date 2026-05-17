"use client";

import { useEffect, useRef, useState } from "react";
import { Station } from "@/lib/api";

interface Props {
  stations: Station[];
  value: Station | null;
  onChange: (station: Station | null) => void;
  placeholder?: string;
  disabled?: boolean;
}

export default function StationSearch({ stations, value, onChange, placeholder = "駅名を入力", disabled }: Props) {
  const [query, setQuery] = useState(value?.name ?? "");
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(value?.name ?? "");
  }, [value]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = query.length === 0
    ? []
    : stations.filter((s) => s.name.includes(query) || s.id.toLowerCase().includes(query.toLowerCase())).slice(0, 10);

  return (
    <div ref={ref} className="relative w-full">
      <input
        type="text"
        value={query}
        disabled={disabled}
        placeholder={placeholder}
        className="w-full rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 shadow-sm focus:border-blue-500 dark:focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:focus:ring-blue-400 disabled:bg-gray-100 dark:disabled:bg-gray-600"
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
          if (e.target.value === "") onChange(null);
        }}
        onFocus={() => setOpen(true)}
      />
      {open && filtered.length > 0 && (
        <ul className="absolute z-10 mt-1 w-full rounded-md border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 shadow-lg">
          {filtered.map((s) => (
            <li
              key={s.id}
              className="cursor-pointer px-3 py-2 text-sm text-gray-900 dark:text-gray-100 hover:bg-blue-50 dark:hover:bg-blue-900/40"
              onMouseDown={() => {
                onChange(s);
                setQuery(s.name);
                setOpen(false);
              }}
            >
              {s.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
