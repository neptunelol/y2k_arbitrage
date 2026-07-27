"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import {
  Camera,
  TrendingUp,
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  Archive,
  Trash2,
  ExternalLink,
  Grid,
  Table,
  Filter,
  ArrowUpDown,
  Zap,
  CheckSquare,
  Square,
  Info,
  Database,
  RefreshCw,
  SlidersHorizontal,
  ChevronRight
} from "lucide-react";

export interface ArbitrageItem {
  id: string;
  model_name: string;
  asking_price: number;
  market_value: number;
  profit_margin: number;
  pipeline_source: "Generic VLM" | "Exact Match";
  damage_severity: "None" | "Minor" | "Major";
  damage_notes: string;
  confidence_score: number; // 0.0 to 1.0
  image_urls: string[];
  status: "pending" | "purchased" | "archived" | "in_transit" | "relisted";
  ebay_url: string;
}

const FALLBACK_DUMMY_DATA: ArbitrageItem[] = [
  {
    id: "arb-101",
    model_name: "Canon PowerShot SD1000 Digital ELPH",
    asking_price: 45.0,
    market_value: 185.0,
    profit_margin: 75.6,
    pipeline_source: "Exact Match",
    damage_severity: "None",
    damage_notes: "Mint condition, original box & battery included.",
    confidence_score: 0.96,
    image_urls: [
      "https://i.ebayimg.com/images/g/85kAAeSwSn9ptVdE/s-l500.jpg",
      "https://i.ebayimg.com/images/g/LDYAAeSw635ptVdE/s-l500.jpg",
      "https://i.ebayimg.com/images/g/NtoAAeSwSHlptVdE/s-l500.jpg"
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/127742115241"
  },
  {
    id: "arb-102",
    model_name: "Sony Cyber-shot DSC-T10 CCD",
    asking_price: 35.0,
    market_value: 145.0,
    profit_margin: 75.8,
    pipeline_source: "Generic VLM",
    damage_severity: "Minor",
    damage_notes: "Minor cosmetic scratches on slider cover.",
    confidence_score: 0.88,
    image_urls: [
      "https://i.ebayimg.com/images/g/ZdgAAeSw-DtqV7Mv/s-l500.jpg",
      "https://i.ebayimg.com/images/g/rEwAAeSw0ZZqV7Mx/s-l500.jpg",
      "https://i.ebayimg.com/images/g/kaoAAeSwws5qV7MW/s-l500.jpg"
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/137515968082"
  },
  {
    id: "arb-103",
    model_name: "Nikon Coolpix S210 Silver",
    asking_price: 55.0,
    market_value: 160.0,
    profit_margin: 65.6,
    pipeline_source: "Exact Match",
    damage_severity: "None",
    damage_notes: "Tested working, lens glass crystal clear.",
    confidence_score: 0.94,
    image_urls: [
      "https://images.unsplash.com/photo-1495707902641-75cac588d2e9?auto=format&fit=crop&w=800&q=80",
      "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=800&q=80"
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/nikon-coolpix-s210"
  },
  {
    id: "arb-104",
    model_name: "Fujifilm FinePix Z33WP Waterproof Y2K",
    asking_price: 65.0,
    market_value: 210.0,
    profit_margin: 69.0,
    pipeline_source: "Generic VLM",
    damage_severity: "None",
    damage_notes: "Waterproof seal intact, vibrant green body.",
    confidence_score: 0.91,
    image_urls: [
      "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?auto=format&fit=crop&w=800&q=80",
      "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?auto=format&fit=crop&w=800&q=80"
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/fujifilm-z33wp"
  }
];

export default function ArbitrageCommandCenter() {
  const [mounted, setMounted] = useState<boolean>(false);
  const [items, setItems] = useState<ArbitrageItem[]>(FALLBACK_DUMMY_DATA);
  const [loading, setLoading] = useState<boolean>(true);
  const [isSupabaseConnected, setIsSupabaseConnected] = useState<boolean>(false);
  const [mode, setMode] = useState<"triage" | "management">("triage");
  const [hoveredCardId, setHoveredCardId] = useState<string | null>(null);

  // Management mode filters & sorting
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [sortField, setSortField] = useState<keyof ArbitrageItem>("profit_margin");
  const [sortAsc, setSortAsc] = useState<boolean>(false);
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  // Prevent hydration mismatch between SSR and client
  useEffect(() => {
    setMounted(true);
  }, []);

  // Fetch real eBay listings photos & details from Supabase
  const fetchSupabaseListings = useCallback(async () => {
    setLoading(true);
    try {
      const { data, error } = await supabase
        .from("listings")
        .select("*")
        .order("created_at", { ascending: false });

      if (error) {
        console.warn("Supabase fetch error, using fallback dataset:", error.message);
        setIsSupabaseConnected(false);
      } else if (data && data.length > 0) {
        setIsSupabaseConnected(true);
        const mappedItems: ArbitrageItem[] = data.map((row: any) => {
          let imgs: string[] = [];
          if (Array.isArray(row.image_urls) && row.image_urls.length > 0) {
            imgs = row.image_urls.map((url: string) =>
              typeof url === "string" ? url.replace("s-l225.jpg", "s-l500.jpg") : url
            );
          } else {
            imgs = [
              "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=800&q=80"
            ];
          }

          let severity: ArbitrageItem["damage_severity"] = "None";
          if (row.damage_severity) {
            const lower = String(row.damage_severity).toLowerCase();
            if (lower.includes("minor")) severity = "Minor";
            else if (lower.includes("major")) severity = "Major";
          }

          let notes = row.damage_notes || "No cosmetic issues flagged.";
          if (notes.includes("Fallback: VLM error")) {
            notes = "Listed from eBay feed. Visual assessment pending.";
          }

          return {
            id: String(row.id),
            model_name: row.model_name || row.title || "eBay Y2K Camera",
            asking_price: Number(row.asking_price) || 0,
            market_value: Number(row.market_value) || 0,
            profit_margin: Number(row.profit_margin) || 0,
            pipeline_source: row.confidence_score > 0 ? "Exact Match" : "Generic VLM",
            damage_severity: severity,
            damage_notes: notes,
            confidence_score: Number(row.confidence_score) || 0.85,
            image_urls: imgs,
            status: "pending",
            ebay_url: row.listing_url || "https://www.ebay.com"
          };
        });
        setItems(mappedItems);
      } else {
        setIsSupabaseConnected(false);
      }
    } catch (err) {
      console.warn("Supabase fetch exception:", err);
      setIsSupabaseConnected(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mounted) {
      fetchSupabaseListings();
    }
  }, [mounted, fetchSupabaseListings]);

  // Pre-fetching eBay URLs and images on client
  useEffect(() => {
    if (!mounted || typeof window === "undefined") return;
    items.forEach((item) => {
      if (item.status === "pending") {
        try {
          const link = document.createElement("link");
          link.rel = "prefetch";
          link.href = item.ebay_url;
          document.head.appendChild(link);

          item.image_urls.forEach((url) => {
            const img = new Image();
            img.src = url;
          });
        } catch (e) {
          // ignore DOM prefetch errors in sandbox
        }
      }
    });
  }, [mounted, items]);

  // Action: Worthy (Purchased + open link + auto-advance)
  const handleWorthy = useCallback((item: ArbitrageItem) => {
    if (typeof window !== "undefined") {
      window.open(item.ebay_url, "_blank", "noopener,noreferrer");
    }
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, status: "purchased" } : i))
    );
  }, []);

  // Action: Unworthy (Archive + prevent default context menu)
  const handleUnworthy = useCallback((item: ArbitrageItem) => {
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, status: "archived" } : i))
    );
  }, []);

  // Global WASD Keyboard Listener
  useEffect(() => {
    if (!mounted || mode !== "triage" || !hoveredCardId) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      const activeItem = items.find(
        (i) => i.id === hoveredCardId && i.status === "pending"
      );
      if (!activeItem) return;

      if (e.key === "w" || e.key === "W") {
        e.preventDefault();
        handleWorthy(activeItem);
      } else if (e.key === "s" || e.key === "S") {
        e.preventDefault();
        handleUnworthy(activeItem);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mounted, mode, hoveredCardId, items, handleWorthy, handleUnworthy]);

  // Active Pending items for Triage Grid
  const pendingItems = useMemo(
    () => items.filter((i) => i.status === "pending"),
    [items]
  );

  // Filtered & Sorted items for Management Table
  const managementItems = useMemo(() => {
    let result = [...items];
    if (sourceFilter !== "all") {
      result = result.filter((i) => i.pipeline_source === sourceFilter);
    }
    if (statusFilter !== "all") {
      result = result.filter((i) => i.status === statusFilter);
    }

    result.sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      if (typeof valA === "number" && typeof valB === "number") {
        return sortAsc ? valA - valB : valB - valA;
      }
      if (typeof valA === "string" && typeof valB === "string") {
        return sortAsc ? valA.localeCompare(valB) : valB.localeCompare(valA);
      }
      return 0;
    });

    return result;
  }, [items, sourceFilter, statusFilter, sortField, sortAsc]);

  // Bulk actions handlers
  const toggleSelectAll = () => {
    if (selectedIds.length === managementItems.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(managementItems.map((i) => i.id));
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  const handleBulkDelete = () => {
    setItems((prev) => prev.filter((i) => !selectedIds.includes(i.id)));
    setSelectedIds([]);
  };

  const handleBulkChangeStatus = (newStatus: ArbitrageItem["status"]) => {
    setItems((prev) =>
      prev.map((i) => (selectedIds.includes(i.id) ? { ...i, status: newStatus } : i))
    );
    setSelectedIds([]);
  };

  const totalPotentialProfit = useMemo(() => {
    return pendingItems.reduce(
      (sum, i) => sum + (i.market_value - i.asking_price),
      0
    );
  }, [pendingItems]);

  if (!mounted) {
    return (
      <div className="min-h-screen bg-[#faf9f6] text-[#111111] font-sans antialiased flex items-center justify-center">
        <div className="text-center space-y-3 font-mono">
          <Camera className="w-8 h-8 text-[#111111] animate-bounce mx-auto" />
          <p className="text-xs uppercase tracking-widest text-[#666666]">
            Initializing Arbitrage Feed...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      suppressHydrationWarning
      className="min-h-screen bg-[#faf9f6] text-[#111111] font-sans antialiased selection:bg-[#111111] selection:text-white"
    >
      {/* Apple-Sleek Egg-White Header with Sharp Corners */}
      <header className="sticky top-0 z-40 bg-[#faf9f6]/90 border-b border-[#e5e2d9] shadow-sm backdrop-blur-md px-8 py-5">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          {/* Brand & Metrics */}
          <div className="flex items-center space-x-4">
            <div className="p-2.5 bg-[#111111] text-white rounded-none">
              <Camera className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-3">
                <h1 className="text-lg font-bold tracking-tight text-[#111111] uppercase font-mono">
                  Arbitrage Command Center
                </h1>
                <span
                  className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded-none border ${
                    isSupabaseConnected
                      ? "bg-[#ecfdf5] border-[#a7f3d0] text-[#047857]"
                      : "bg-[#fffbebf] border-[#fde68a] text-[#b45309]"
                  }`}
                >
                  {isSupabaseConnected ? "Live Supabase Sync" : "Cached Feed"}
                </span>
              </div>
              <div className="flex items-center space-x-4 text-xs text-[#666666] mt-1 font-mono">
                <span className="font-semibold text-[#111111]">
                  Est. Profit Margin:{" "}
                  <span className="text-[#059669]">
                    +${totalPotentialProfit.toFixed(2)}
                  </span>
                </span>
                <span>/</span>
                <span>Active Listings: {pendingItems.length}</span>
              </div>
            </div>
          </div>

          {/* Mode Switcher - Sharp Egg-White / Obsidian Contrast */}
          <div className="flex items-center space-x-3">
            <button
              onClick={fetchSupabaseListings}
              title="Refresh Supabase eBay listings"
              className="p-2.5 border border-[#e2dfd7] bg-white hover:bg-[#f0eee9] text-[#111111] rounded-none transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            </button>

            <div className="flex items-center bg-[#eae7df] p-1 border border-[#dcd8cc] rounded-none shadow-inner">
              <button
                onClick={() => setMode("triage")}
                className={`flex items-center px-5 py-2 text-xs font-bold uppercase tracking-wider rounded-none transition-all duration-200 ${
                  mode === "triage"
                    ? "bg-[#111111] text-white shadow-sm"
                    : "text-[#555555] hover:text-[#111111]"
                }`}
              >
                <Grid className="w-3.5 h-3.5 mr-2" />
                Triage Mode
              </button>
              <button
                onClick={() => setMode("management")}
                className={`flex items-center px-5 py-2 text-xs font-bold uppercase tracking-wider rounded-none transition-all duration-200 ${
                  mode === "management"
                    ? "bg-[#111111] text-white shadow-sm"
                    : "text-[#555555] hover:text-[#111111]"
                }`}
              >
                <Table className="w-3.5 h-3.5 mr-2" />
                Management ({items.length})
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content Body */}
      <main className="max-w-7xl mx-auto px-8 py-8">
        {mode === "triage" ? (
          <div>
            {/* Minimalist Apple-Style Keyboard Shortcut Legend */}
            <div className="mb-8 p-4 bg-white border border-[#e2dfd7] rounded-none flex flex-col md:flex-row items-center justify-between text-xs text-[#555555] font-mono shadow-sm">
              <div className="flex items-center space-x-6">
                <span className="font-bold text-[#111111] uppercase tracking-wider flex items-center">
                  <SlidersHorizontal className="w-3.5 h-3.5 mr-2" />
                  Interaction Mechanics:
                </span>
                <span>
                  <kbd className="px-2 py-0.5 bg-[#f0eee9] border border-[#d6d2c4] text-[#111111] font-bold">
                    W
                  </kbd>{" "}
                  / <span className="text-[#111111] font-semibold">Left-Click</span> = Open eBay & Buy
                </span>
                <span>
                  <kbd className="px-2 py-0.5 bg-[#f0eee9] border border-[#d6d2c4] text-[#111111] font-bold">
                    S
                  </kbd>{" "}
                  / <span className="text-[#111111] font-semibold">Right-Click</span> = Archive
                </span>
                <span>
                  <kbd className="px-2 py-0.5 bg-[#f0eee9] border border-[#d6d2c4] text-[#111111] font-bold">
                    Scroll Wheel
                  </kbd>{" "}
                  = Cycle Listing Photos
                </span>
              </div>
              <span className="text-[#888888] text-[11px] mt-2 md:mt-0">
                Zero-Friction Auto-Advance Active
              </span>
            </div>

            {/* Apple-Sleek Sharp Grid */}
            {pendingItems.length === 0 ? (
              <div className="text-center py-32 border border-[#e2dfd7] bg-white rounded-none shadow-sm">
                <CheckCircle2 className="w-10 h-10 text-[#059669] mx-auto mb-3" />
                <h3 className="text-base font-bold uppercase tracking-wider text-[#111111]">
                  Feed Triage Complete
                </h3>
                <p className="text-xs text-[#666666] mt-1 font-mono">
                  All active eBay listing photos reviewed. Switch to Management View to inspect database.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-8">
                {pendingItems.map((item) => (
                  <SleekEggWhiteCard
                    key={item.id}
                    item={item}
                    isHovered={hoveredCardId === item.id}
                    onHoverChange={(hovering) =>
                      setHoveredCardId(hovering ? item.id : null)
                    }
                    onWorthy={() => handleWorthy(item)}
                    onUnworthy={() => handleUnworthy(item)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          /* Management View: Egg-White Sharp Data Table */
          <div className="space-y-6">
            {/* Filter Bar */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-5 border border-[#e2dfd7] rounded-none shadow-sm">
              <div className="flex items-center space-x-4 w-full sm:w-auto font-mono text-xs">
                <div className="flex items-center text-[#111111] font-bold uppercase">
                  <Filter className="w-3.5 h-3.5 mr-2" /> Filters:
                </div>

                <select
                  value={sourceFilter}
                  onChange={(e) => setSourceFilter(e.target.value)}
                  className="bg-[#faf9f6] border border-[#d6d2c4] text-xs text-[#111111] rounded-none px-3 py-2 focus:outline-none focus:border-[#111111]"
                >
                  <option value="all">All Sources</option>
                  <option value="Exact Match">Exact Match</option>
                  <option value="Generic VLM">Generic VLM</option>
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="bg-[#faf9f6] border border-[#d6d2c4] text-xs text-[#111111] rounded-none px-3 py-2 focus:outline-none focus:border-[#111111]"
                >
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="purchased">Purchased</option>
                  <option value="archived">Archived</option>
                  <option value="in_transit">In Transit</option>
                  <option value="relisted">Relisted</option>
                </select>
              </div>

              <div className="text-xs text-[#666666] font-mono">
                Showing {managementItems.length} of {items.length} records
              </div>
            </div>

            {/* Bulk Floating Action Bar */}
            {selectedIds.length > 0 && (
              <div className="sticky top-24 z-30 bg-[#111111] text-white border border-[#333333] rounded-none p-4 shadow-xl flex items-center justify-between animate-in fade-in duration-200 font-mono text-xs">
                <div className="flex items-center space-x-3">
                  <CheckSquare className="w-4 h-4 text-emerald-400" />
                  <span className="font-bold">{selectedIds.length} item(s) selected</span>
                </div>

                <div className="flex items-center space-x-3">
                  <select
                    onChange={(e) => {
                      if (e.target.value) {
                        handleBulkChangeStatus(
                          e.target.value as ArbitrageItem["status"]
                        );
                        e.target.value = "";
                      }
                    }}
                    className="bg-[#222222] border border-[#444444] text-xs text-white rounded-none px-3 py-1.5 focus:outline-none"
                  >
                    <option value="">Change Status...</option>
                    <option value="pending">Set Pending</option>
                    <option value="purchased">Set Purchased</option>
                    <option value="in_transit">Set In Transit</option>
                    <option value="relisted">Set Relisted</option>
                    <option value="archived">Set Archived</option>
                  </select>

                  <button
                    onClick={() => handleBulkChangeStatus("archived")}
                    className="px-4 py-1.5 bg-[#333333] hover:bg-[#444444] text-white rounded-none transition-colors uppercase font-bold text-[11px]"
                  >
                    Archive
                  </button>

                  <button
                    onClick={handleBulkDelete}
                    className="px-4 py-1.5 bg-rose-600 hover:bg-rose-700 text-white rounded-none transition-colors uppercase font-bold text-[11px]"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}

            {/* High-Density Apple Table with Sharp Corners */}
            <div className="border border-[#e2dfd7] bg-white rounded-none shadow-sm overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-[#111111] border-collapse">
                  <thead className="bg-[#f3f1ec] text-[#444444] uppercase font-mono text-[11px] font-bold border-b border-[#e2dfd7]">
                    <tr>
                      <th className="p-3.5 w-10 text-center">
                        <button onClick={toggleSelectAll}>
                          {selectedIds.length === managementItems.length &&
                          managementItems.length > 0 ? (
                            <CheckSquare className="w-4 h-4 text-[#111111]" />
                          ) : (
                            <Square className="w-4 h-4 text-[#999999]" />
                          )}
                        </button>
                      </th>
                      <th
                        className="p-3.5 cursor-pointer hover:text-black"
                        onClick={() => {
                          setSortField("model_name");
                          setSortAsc(!sortAsc);
                        }}
                      >
                        <div className="flex items-center space-x-1">
                          <span>Listing / Model</span>
                          <ArrowUpDown className="w-3 h-3 ml-1" />
                        </div>
                      </th>
                      <th className="p-3.5">Status</th>
                      <th
                        className="p-3.5 cursor-pointer hover:text-black font-mono"
                        onClick={() => {
                          setSortField("asking_price");
                          setSortAsc(!sortAsc);
                        }}
                      >
                        Asking
                      </th>
                      <th
                        className="p-3.5 cursor-pointer hover:text-black font-mono"
                        onClick={() => {
                          setSortField("market_value");
                          setSortAsc(!sortAsc);
                        }}
                      >
                        Market
                      </th>
                      <th
                        className="p-3.5 cursor-pointer hover:text-black font-mono text-right"
                        onClick={() => {
                          setSortField("profit_margin");
                          setSortAsc(!sortAsc);
                        }}
                      >
                        Profit %
                      </th>
                      <th className="p-3.5">Source</th>
                      <th className="p-3.5">Damage</th>
                      <th className="p-3.5 font-mono">Confidence</th>
                      <th className="p-3.5 text-right">eBay Link</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#eeebe3] font-sans">
                    {managementItems.length === 0 ? (
                      <tr>
                        <td colSpan={10} className="p-12 text-center text-[#888888] font-mono">
                          No matching listings found in database.
                        </td>
                      </tr>
                    ) : (
                      managementItems.map((item) => {
                        const isSelected = selectedIds.includes(item.id);
                        return (
                          <tr
                            key={item.id}
                            className={`hover:bg-[#faf9f6] transition-colors ${
                              isSelected ? "bg-[#f0eee9]" : ""
                            }`}
                          >
                            <td className="p-3.5 text-center">
                              <button onClick={() => toggleSelect(item.id)}>
                                {isSelected ? (
                                  <CheckSquare className="w-4 h-4 text-[#111111]" />
                                ) : (
                                  <Square className="w-4 h-4 text-[#cccccc]" />
                                )}
                              </button>
                            </td>
                            <td className="p-3.5 font-semibold text-[#111111]">
                              <div className="flex items-center space-x-3">
                                <img
                                  src={item.image_urls[0]}
                                  alt=""
                                  className="w-9 h-9 object-cover rounded-none border border-[#e2dfd7]"
                                />
                                <span className="truncate max-w-xs">{item.model_name}</span>
                              </div>
                            </td>
                            <td className="p-3.5">
                              <span
                                className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded-none border ${
                                  item.status === "purchased"
                                    ? "bg-[#ecfdf5] border-[#a7f3d0] text-[#047857]"
                                    : item.status === "archived"
                                    ? "bg-[#f3f4f6] border-[#e5e7eb] text-[#6b7280]"
                                    : item.status === "in_transit"
                                    ? "bg-[#fffbebf] border-[#fde68a] text-[#b45309]"
                                    : item.status === "relisted"
                                    ? "bg-[#eff6ff] border-[#bfdbfe] text-[#1d4ed8]"
                                    : "bg-[#f5f3ff] border-[#ddd6fe] text-[#6d28d9]"
                                }`}
                              >
                                {item.status}
                              </span>
                            </td>
                            <td className="p-3.5 font-mono">${item.asking_price.toFixed(2)}</td>
                            <td className="p-3.5 font-mono">${item.market_value.toFixed(2)}</td>
                            <td className="p-3.5 font-mono font-bold text-right">
                              <span
                                className={
                                  item.profit_margin > 40
                                    ? "text-[#059669] font-extrabold"
                                    : "text-[#444444]"
                                }
                              >
                                +{item.profit_margin.toFixed(1)}%
                              </span>
                            </td>
                            <td className="p-3.5">
                              <span className="px-2 py-0.5 text-[10px] font-mono rounded-none border border-[#d6d2c4] bg-[#f7f6f2] text-[#333333]">
                                {item.pipeline_source}
                              </span>
                            </td>
                            <td className="p-3.5">
                              <span
                                className={`font-mono text-xs font-semibold ${
                                  item.damage_severity === "None"
                                    ? "text-[#059669]"
                                    : item.damage_severity === "Minor"
                                    ? "text-[#d97706]"
                                    : "text-[#dc2626]"
                                }`}
                              >
                                {item.damage_severity}
                              </span>
                            </td>
                            <td className="p-3.5 font-mono">
                              {(item.confidence_score * 100).toFixed(0)}%
                            </td>
                            <td className="p-3.5 text-right">
                              <a
                                href={item.ebay_url}
                                target="_blank"
                                rel="noreferrer"
                                className="p-2 inline-block text-[#111111] hover:bg-[#111111] hover:text-white border border-[#e2dfd7] rounded-none transition-colors"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </a>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

{/* Apple-Sleek Egg-White Card Component with Sharp Corners */}
function SleekEggWhiteCard({
  item,
  isHovered,
  onHoverChange,
  onWorthy,
  onUnworthy
}: {
  item: ArbitrageItem;
  isHovered: boolean;
  onHoverChange: (hovered: boolean) => void;
  onWorthy: () => void;
  onUnworthy: () => void;
}) {
  const [imgIdx, setImgIdx] = useState(0);
  const cardRef = useRef<HTMLDivElement>(null);

  // Non-passive wheel event listener for image cycling without page scroll
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.deltaY > 0) {
        setImgIdx((prev) => (prev + 1) % item.image_urls.length);
      } else if (e.deltaY < 0) {
        setImgIdx(
          (prev) => (prev - 1 + item.image_urls.length) % item.image_urls.length
        );
      }
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [item.image_urls.length]);

  return (
    <div
      ref={cardRef}
      onMouseEnter={() => onHoverChange(true)}
      onMouseLeave={() => onHoverChange(false)}
      onClick={onWorthy}
      onContextMenu={(e) => {
        e.preventDefault();
        onUnworthy();
      }}
      className={`relative h-[420px] rounded-none overflow-hidden cursor-pointer select-none bg-white border transition-all duration-300 ${
        isHovered
          ? "border-[#111111] shadow-xl translate-y-[-2px]"
          : "border-[#e2dfd7] shadow-sm hover:border-[#888888]"
      }`}
    >
      {/* Primary eBay Listing Photo */}
      <img
        src={item.image_urls[imgIdx]}
        alt={item.model_name}
        className={`absolute inset-0 w-full h-full object-cover rounded-none transition-all duration-500 ${
          isHovered ? "scale-105 filter brightness-95" : "brightness-[0.98]"
        }`}
      />

      {/* Non-Hovered Minimal Egg-White Bottom Bar */}
      {!isHovered && (
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-white via-white/90 to-transparent pt-12 pb-5 px-5 flex flex-col justify-end">
          <div className="space-y-1">
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-bold text-sm text-[#111111] line-clamp-1">
                {item.model_name}
              </h3>
              <span
                className={`text-sm font-extrabold font-mono flex-shrink-0 ${
                  item.profit_margin > 40 ? "text-[#059669]" : "text-[#111111]"
                }`}
              >
                +{item.profit_margin.toFixed(0)}%
              </span>
            </div>
            <div className="flex items-center justify-between text-xs text-[#666666] font-mono">
              <span>${item.asking_price.toFixed(2)} asking</span>
              <span className="text-[10px] uppercase tracking-wider text-[#999999]">
                Hover to expand
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Hover Deep-Dive Overlay - Apple Egg-White Minimalist Card */}
      {isHovered && (
        <div className="absolute inset-0 bg-[#faf9f6]/95 backdrop-blur-md p-6 flex flex-col justify-between animate-in fade-in duration-200 text-xs border border-[#111111]">
          {/* Top Info Badges & Image Indicators */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="px-2 py-0.5 text-[10px] font-mono uppercase font-bold border border-[#d6d2c4] bg-white text-[#111111]">
                {item.pipeline_source}
              </span>

              {/* Photo Index Indicator */}
              <div className="flex items-center space-x-1.5 font-mono text-[10px] text-[#666666]">
                <span>
                  Photo {imgIdx + 1}/{item.image_urls.length}
                </span>
              </div>
            </div>

            <h3 className="font-bold text-sm text-[#111111] line-clamp-2 leading-tight">
              {item.model_name}
            </h3>
          </div>

          {/* Financial Breakdown Grid */}
          <div className="grid grid-cols-2 gap-3 bg-white p-3.5 border border-[#e2dfd7] rounded-none">
            <div>
              <span className="text-[10px] text-[#777777] block uppercase font-mono">
                Asking Price
              </span>
              <span className="text-base font-bold font-mono text-[#111111]">
                ${item.asking_price.toFixed(2)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-[#777777] block uppercase font-mono">
                Market Value
              </span>
              <span className="text-base font-bold font-mono text-[#059669]">
                ${item.market_value.toFixed(2)}
              </span>
            </div>
          </div>

          {/* Visual Assessment & Notes */}
          <div className="space-y-1 bg-white p-3 border border-[#e2dfd7] rounded-none">
            <div className="flex items-center justify-between text-[11px] font-mono">
              <span className="text-[#666666]">Damage Status:</span>
              <span
                className={`font-bold ${
                  item.damage_severity === "None"
                    ? "text-[#059669]"
                    : item.damage_severity === "Minor"
                    ? "text-[#d97706]"
                    : "text-[#dc2626]"
                }`}
              >
                {item.damage_severity}
              </span>
            </div>
            <p className="text-[11px] text-[#444444] italic line-clamp-2 leading-relaxed">
              "{item.damage_notes}"
            </p>
          </div>

          {/* VLM Confidence Score Progress Bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-[10px] text-[#666666] font-mono">
              <span>Confidence Score</span>
              <span className="text-[#111111] font-bold">
                {(item.confidence_score * 100).toFixed(0)}%
              </span>
            </div>
            <div className="w-full bg-[#e5e2d9] h-1 rounded-none overflow-hidden">
              <div
                className="bg-[#111111] h-full rounded-none transition-all duration-300"
                style={{ width: `${item.confidence_score * 100}%` }}
              />
            </div>
          </div>

          {/* Card Footer Actions */}
          <div className="flex items-center justify-between text-[11px] pt-2 font-mono border-t border-[#e2dfd7]">
            <span className="text-[#059669] font-bold flex items-center">
              [W] Buy Listing
            </span>
            <span className="text-[#dc2626] font-bold flex items-center">
              [S] Archive
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
