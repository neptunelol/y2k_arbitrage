"use client";

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { supabase } from "@/lib/supabase";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  ColumnDef,
  SortingState,
  RowSelectionState,
} from "@tanstack/react-table";
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
  RefreshCw,
  CopyX,
  Layers,
  Check,
  HelpCircle,
  X,
  Activity,
  PackageCheck,
  Truck,
  RotateCcw,
  DollarSign,
  ChevronDown,
  ChevronUp,
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
  status: "pending" | "purchased" | "archived" | "in_transit" | "testing" | "relisted" | "sold";
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
      "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?auto=format&fit=crop&w=800&q=80",
      "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=800&q=80",
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/127742115241",
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
      "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?auto=format&fit=crop&w=800&q=80",
      "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?auto=format&fit=crop&w=800&q=80",
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/137515968082",
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
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/nikon-coolpix-s210",
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
    ],
    status: "pending",
    ebay_url: "https://www.ebay.com/itm/fujifilm-z33wp",
  },
];

const deduplicateListings = (
  itemsList: ArbitrageItem[]
): { unique: ArbitrageItem[]; removedCount: number } => {
  const seenUrls = new Set<string>();
  const seenModelPrices = new Set<string>();
  const unique: ArbitrageItem[] = [];

  itemsList.forEach((item) => {
    const canonicalUrl = item.ebay_url ? item.ebay_url.split("?")[0].toLowerCase().trim() : item.id;
    const modelPriceKey = `${item.model_name.toLowerCase().trim()}_${item.asking_price}`;

    if (seenUrls.has(canonicalUrl) || seenModelPrices.has(modelPriceKey)) {
      return;
    }

    seenUrls.add(canonicalUrl);
    seenModelPrices.add(modelPriceKey);
    unique.push(item);
  });

  return {
    unique,
    removedCount: itemsList.length - unique.length,
  };
};

export default function ArbitrageCommandCenter() {
  const [mounted, setMounted] = useState<boolean>(false);
  const [items, setItems] = useState<ArbitrageItem[]>(FALLBACK_DUMMY_DATA);
  const [loading, setLoading] = useState<boolean>(true);
  const [isSupabaseConnected, setIsSupabaseConnected] = useState<boolean>(false);
  const [mode, setMode] = useState<"triage" | "wanted" | "management">("triage");
  const [selectedCardId, setSelectedCardId] = useState<string | null>(null);
  const [animatingCardId, setAnimatingCardId] = useState<{ id: string; action: "purchase" | "archive" } | null>(null);
  const [notification, setNotification] = useState<string | null>(null);
  const [isCheatSheetOpen, setIsCheatSheetOpen] = useState<boolean>(false);

  // Scanner status state
  const [isScanning, setIsScanning] = useState<boolean>(false);
  const [scanType, setScanType] = useState<string | null>(null);
  const [lastScanTime, setLastScanTime] = useState<string>("Just now");

  // Detail Modal State
  const [detailModalItem, setDetailModalItem] = useState<ArbitrageItem | null>(null);

  // TanStack Table states
  const [sorting, setSorting] = useState<SortingState>([{ id: "profit_margin", desc: true }]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [sourceFilter, setSourceFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  const backendApiUrl = process.env.NEXT_PUBLIC_BACKEND_API_URL || "http://localhost:8000";

  useEffect(() => {
    setMounted(true);
    setLastScanTime(new Date().toLocaleTimeString());
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        const hasSeen = window.localStorage.getItem("hasSeenCheatSheet");
        if (!hasSeen) {
          setIsCheatSheetOpen(true);
          window.localStorage.setItem("hasSeenCheatSheet", "true");
        }
      }
    } catch (e) {
      console.warn("LocalStorage access notice:", e);
    }
  }, []);

  const handleDeduplicate = useCallback(() => {
    setItems((prev) => {
      const { unique, removedCount } = deduplicateListings(prev);
      if (removedCount > 0) {
        setNotification(`Deduplication Complete: Removed ${removedCount} duplicate listing(s).`);
      } else {
        setNotification("Feed Clean: No duplicate listings found.");
      }
      setTimeout(() => setNotification(null), 4000);
      return unique;
    });
  }, []);

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
        const { unique } = deduplicateListings(FALLBACK_DUMMY_DATA);
        setItems(unique);
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
              "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?auto=format&fit=crop&w=800&q=80",
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
            ebay_url: row.listing_url || "https://www.ebay.com",
          };
        });

        const { unique, removedCount } = deduplicateListings(mappedItems);
        setItems(unique);
        if (removedCount > 0) {
          setNotification(`Auto-Deduplication: Filtered out ${removedCount} duplicate listing(s).`);
          setTimeout(() => setNotification(null), 4000);
        }
      } else {
        setIsSupabaseConnected(true);
        const { unique } = deduplicateListings(FALLBACK_DUMMY_DATA);
        setItems(unique);
      }
    } catch (err) {
      console.warn("Supabase fetch exception, using fallback dataset:", err);
      setIsSupabaseConnected(false);
      const { unique } = deduplicateListings(FALLBACK_DUMMY_DATA);
      setItems(unique);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (mounted) {
      fetchSupabaseListings();
    }
  }, [mounted, fetchSupabaseListings]);

  // Handle on-demand Fast-Track & Slow-Track scanning
  const handleTriggerScan = async (type: "fast" | "slow") => {
    setIsScanning(true);
    const scanLabel = type === "fast" ? "Fast-Track" : "Slow-Track";
    setScanType(scanLabel);
    setNotification(`Initiating ${scanLabel} Scan...`);
    try {
      const res = await fetch(`${backendApiUrl}/api/scan/${type}`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }
      const json = await res.json();
      setNotification(`Scan dispatched: ${json.message || `${scanLabel} scan initiated.`}`);
      setLastScanTime(new Date().toLocaleTimeString());
      setTimeout(() => fetchSupabaseListings(), 3000);
    } catch (err) {
      console.warn(`[API NOTICE] Backend service at ${backendApiUrl} unavailable:`, err);
      setNotification(`Backend API offline. Ensure backend is running via 'cd backend && python main.py'`);
      setLastScanTime(new Date().toLocaleTimeString());
    } finally {
      setIsScanning(false);
      setScanType(null);
      setTimeout(() => setNotification(null), 5000);
    }
  };

  // Handle purging database records to restart fresh VLM scan
  const handlePurgeListings = async () => {
    if (!window.confirm("Are you sure you want to purge all listings to restart with fresh VLM scans?")) {
      return;
    }
    setNotification("Purging database records...");
    try {
      const res = await fetch(`${backendApiUrl}/api/listings/clear`, { method: "POST" });
      const json = await res.json();
      setNotification(`Database Cleared: Removed ${json.deleted_count || 0} listing(s).`);
      setItems([]);
    } catch (err) {
      console.warn("Purge error:", err);
      setItems([]);
      setNotification("Feed cleared locally.");
    } finally {
      setTimeout(() => setNotification(null), 4000);
    }
  };

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

  const pendingItems = useMemo(
    () => items.filter((i) => i.status === "pending"),
    [items]
  );

  const wantedItems = useMemo(
    () => items.filter((i) => i.status === "purchased"),
    [items]
  );

  const handleWorthy = useCallback((item: ArbitrageItem) => {
    setAnimatingCardId({ id: item.id, action: "purchase" });
    if (typeof window !== "undefined") {
      window.open(item.ebay_url, "_blank", "noopener,noreferrer");
    }
    setNotification(`Saved "${item.model_name}" to "I Want It" list & opening eBay...`);
    setTimeout(() => setNotification(null), 3500);

    // Auto-advance selection to adjacent card in pendingItems
    setItems((prev) => {
      const pendingList = prev.filter((i) => i.status === "pending");
      const currentIdx = pendingList.findIndex((i) => i.id === item.id);
      const remaining = pendingList.filter((i) => i.id !== item.id);
      const nextItem = remaining[currentIdx] || remaining[currentIdx - 1] || null;
      setSelectedCardId(nextItem ? nextItem.id : null);

      return prev.map((i) => (i.id === item.id ? { ...i, status: "purchased" } : i));
    });

    setTimeout(() => {
      setAnimatingCardId(null);
    }, 300);
  }, []);

  const handleUnworthy = useCallback((item: ArbitrageItem) => {
    setAnimatingCardId({ id: item.id, action: "archive" });
    setNotification(`Archived "${item.model_name}".`);
    setTimeout(() => setNotification(null), 3500);

    // Auto-advance selection to adjacent card in pendingItems
    setItems((prev) => {
      const pendingList = prev.filter((i) => i.status === "pending");
      const currentIdx = pendingList.findIndex((i) => i.id === item.id);
      const remaining = pendingList.filter((i) => i.id !== item.id);
      const nextItem = remaining[currentIdx] || remaining[currentIdx - 1] || null;
      setSelectedCardId(nextItem ? nextItem.id : null);

      return prev.map((i) => (i.id === item.id ? { ...i, status: "archived" } : i));
    });

    setTimeout(() => {
      setAnimatingCardId(null);
    }, 300);
  }, []);

  // Global Keyboard Shortcuts (Tab / 1 / 2 / 3 for mode, ? for cheat sheet, W / S / Arrows for card actions)
  useEffect(() => {
    if (!mounted) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "?") {
        e.preventDefault();
        setIsCheatSheetOpen((prev) => !prev);
        return;
      }

      if (e.key === "Tab") {
        e.preventDefault();
        setMode((prev) => (prev === "triage" ? "wanted" : prev === "wanted" ? "management" : "triage"));
        return;
      }
      if (e.key === "1") {
        setMode("triage");
        return;
      }
      if (e.key === "2") {
        setMode("wanted");
        return;
      }
      if (e.key === "3") {
        setMode("management");
        return;
      }

      if (mode === "triage") {
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          e.preventDefault();
          const currentIdx = pendingItems.findIndex((i) => i.id === selectedCardId);
          const nextIdx = currentIdx < pendingItems.length - 1 ? currentIdx + 1 : 0;
          if (pendingItems[nextIdx]) {
            setSelectedCardId(pendingItems[nextIdx].id);
          }
          return;
        }

        if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          e.preventDefault();
          const currentIdx = pendingItems.findIndex((i) => i.id === selectedCardId);
          const prevIdx = currentIdx > 0 ? currentIdx - 1 : pendingItems.length - 1;
          if (pendingItems[prevIdx]) {
            setSelectedCardId(pendingItems[prevIdx].id);
          }
          return;
        }

        const targetId = selectedCardId || pendingItems[0]?.id;
        const activeItem = items.find((i) => i.id === targetId && i.status === "pending");
        if (!activeItem) return;

        if (e.key === "w" || e.key === "W") {
          e.preventDefault();
          handleWorthy(activeItem);
        } else if (e.key === "s" || e.key === "S") {
          e.preventDefault();
          handleUnworthy(activeItem);
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mounted, mode, selectedCardId, pendingItems, items, handleWorthy, handleUnworthy]);

  // Management items for TanStack Table
  const filteredManagementItems = useMemo(() => {
    let result = [...items];
    if (sourceFilter !== "all") {
      result = result.filter((i) => i.pipeline_source === sourceFilter);
    }
    if (statusFilter !== "all") {
      result = result.filter((i) => i.status === statusFilter);
    }
    return result;
  }, [items, sourceFilter, statusFilter]);

  // TanStack Table Setup
  const columns = useMemo<ColumnDef<ArbitrageItem>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <button
            onClick={table.getToggleAllRowsSelectedHandler()}
            className="p-1 hover:text-white"
          >
            {table.getIsAllRowsSelected() ? (
              <CheckSquare className="w-4 h-4 text-[#00ff88]" />
            ) : (
              <Square className="w-4 h-4 text-zinc-500" />
            )}
          </button>
        ),
        cell: ({ row }) => (
          <button
            onClick={row.getToggleSelectedHandler()}
            className="p-1 hover:text-white"
          >
            {row.getIsSelected() ? (
              <CheckSquare className="w-4 h-4 text-[#00ff88]" />
            ) : (
              <Square className="w-4 h-4 text-zinc-600" />
            )}
          </button>
        ),
      },
      {
        accessorKey: "model_name",
        header: ({ column }) => (
          <button
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="flex items-center space-x-1 hover:text-white"
          >
            <span>Model / Listing</span>
            <ArrowUpDown className="w-3 h-3 ml-1" />
          </button>
        ),
        cell: ({ row, getValue }) => (
          <div className="flex items-center space-x-3 h-12">
            <img
              src={row.original.image_urls[0]}
              alt=""
              className="w-10 h-10 object-cover rounded-none border border-zinc-800"
            />
            <span className="truncate max-w-xs font-semibold text-zinc-100">
              {String(getValue())}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "status",
        header: "Status",
        cell: ({ getValue }) => {
          const val = String(getValue());
          return (
            <span
              className={`px-2 py-0.5 text-[10px] font-mono font-bold uppercase rounded-none border ${
                val === "purchased"
                  ? "bg-[#00ff88]/10 border-[#00ff88]/30 text-[#00ff88]"
                  : val === "archived"
                  ? "bg-zinc-800 border-zinc-700 text-zinc-400"
                  : val === "in_transit"
                  ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                  : val === "testing"
                  ? "bg-cyan-500/10 border-cyan-500/30 text-cyan-400"
                  : val === "relisted"
                  ? "bg-blue-500/10 border-blue-500/30 text-blue-400"
                  : val === "sold"
                  ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                  : "bg-zinc-900 border-zinc-700 text-zinc-300"
              }`}
            >
              {val}
            </span>
          );
        },
      },
      {
        accessorKey: "asking_price",
        header: ({ column }) => (
          <button
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="flex items-center space-x-1 hover:text-white font-mono"
          >
            <span>Asking</span>
            <ArrowUpDown className="w-3 h-3 ml-1" />
          </button>
        ),
        cell: ({ getValue }) => (
          <span className="font-mono text-zinc-200">${Number(getValue()).toFixed(2)}</span>
        ),
      },
      {
        accessorKey: "market_value",
        header: ({ column }) => (
          <button
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="flex items-center space-x-1 hover:text-white font-mono"
          >
            <span>Market</span>
            <ArrowUpDown className="w-3 h-3 ml-1" />
          </button>
        ),
        cell: ({ getValue }) => (
          <span className="font-mono text-emerald-400">${Number(getValue()).toFixed(2)}</span>
        ),
      },
      {
        accessorKey: "profit_margin",
        header: ({ column }) => (
          <button
            onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
            className="flex items-center space-x-1 hover:text-white font-mono text-right"
          >
            <span>Margin %</span>
            <ArrowUpDown className="w-3 h-3 ml-1" />
          </button>
        ),
        cell: ({ getValue }) => {
          const val = Number(getValue());
          let colorClass = "text-zinc-300";
          if (val > 40) colorClass = "text-[#00ff88] font-bold";
          else if (val >= 25) colorClass = "text-[#4ade80]";
          else if (val < 0) colorClass = "text-[#ff4444]";
          return <span className={`font-mono text-right ${colorClass}`}>+{val.toFixed(1)}%</span>;
        },
      },
      {
        accessorKey: "pipeline_source",
        header: "Source",
        cell: ({ getValue }) => {
          const val = String(getValue());
          return (
            <span
              className={
                val === "Exact Match"
                  ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-full px-2.5 py-0.5 text-xs font-mono"
                  : "bg-purple-600/20 text-purple-400 border border-purple-500/30 rounded-full px-2.5 py-0.5 text-xs font-mono"
              }
            >
              {val}
            </span>
          );
        },
      },
      {
        accessorKey: "damage_severity",
        header: "Damage",
        cell: ({ getValue }) => {
          const val = String(getValue());
          return (
            <span
              className={`font-mono text-xs font-semibold ${
                val === "None" ? "text-emerald-400" : val === "Minor" ? "text-amber-400" : "text-red-400"
              }`}
            >
              {val}
            </span>
          );
        },
      },
      {
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <div className="flex items-center space-x-2 text-right">
            <button
              onClick={() => setExpandedRowId(expandedRowId === row.original.id ? null : row.original.id)}
              className="p-1 hover:text-white text-zinc-400"
              title="Expand row details"
            >
              {expandedRowId === row.original.id ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            <a
              href={row.original.ebay_url}
              target="_blank"
              rel="noreferrer"
              className="p-1.5 text-zinc-400 hover:text-white border border-zinc-800 transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        ),
      },
    ],
    [expandedRowId]
  );

  const table = useReactTable({
    data: filteredManagementItems,
    columns,
    state: {
      sorting,
      rowSelection,
    },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  });

  const selectedRows = table.getSelectedRowModel().rows;

  const handleBulkStatusChange = (newStatus: ArbitrageItem["status"]) => {
    const selectedIdsList = selectedRows.map((r) => r.original.id);
    setItems((prev) =>
      prev.map((i) => (selectedIdsList.includes(i.id) ? { ...i, status: newStatus } : i))
    );
    setRowSelection({});
    setNotification(`Updated ${selectedIdsList.length} item(s) to status: ${newStatus}`);
    setTimeout(() => setNotification(null), 3000);
  };

  const handleBulkDelete = () => {
    const selectedIdsList = selectedRows.map((r) => r.original.id);
    setItems((prev) => prev.filter((i) => !selectedIdsList.includes(i.id)));
    setRowSelection({});
    setNotification(`Deleted ${selectedIdsList.length} item(s) from database.`);
    setTimeout(() => setNotification(null), 3000);
  };

  // Stats calculation
  const totalListings = items.length;
  const profitableCount = pendingItems.filter((i) => i.profit_margin >= 25).length;
  const avgMargin =
    pendingItems.length > 0
      ? pendingItems.reduce((sum, i) => sum + i.profit_margin, 0) / pendingItems.length
      : 0;
  const totalPotentialProfit = pendingItems.reduce(
    (sum, i) => sum + (i.market_value - i.asking_price),
    0
  );
  const exactCount = items.filter((i) => i.pipeline_source === "Exact Match").length;
  const genericCount = items.filter((i) => i.pipeline_source === "Generic VLM").length;

  if (!mounted) {
    return (
      <div className="min-h-screen bg-[#000000] text-white font-sans antialiased flex items-center justify-center">
        <div className="text-center space-y-3 font-mono">
          <Camera className="w-8 h-8 text-[#00ff88] animate-bounce mx-auto" />
          <p className="text-xs uppercase tracking-widest text-zinc-400">
            Initializing Brutalist OLED Command Center...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div
      suppressHydrationWarning
      className="min-h-screen bg-[#000000] text-white font-sans antialiased selection:bg-[#00ff88] selection:text-black"
    >
      {/* Toast Notification Banner */}
      {notification && (
        <div className="fixed bottom-6 right-6 z-50 bg-zinc-900 text-white px-5 py-3 border border-zinc-700 shadow-2xl rounded-none font-mono text-xs flex items-center space-x-3 animate-in slide-in-from-bottom-3 duration-200">
          <Sparkles className="w-4 h-4 text-[#00ff88]" />
          <span>{notification}</span>
        </div>
      )}

      {/* Keyboard Shortcuts Cheat Sheet Overlay Modal */}
      {isCheatSheetOpen && (
        <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 text-zinc-100 max-w-lg w-full p-6 space-y-6 shadow-2xl relative">
            <button
              onClick={() => setIsCheatSheetOpen(false)}
              className="absolute top-4 right-4 text-zinc-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            <div className="flex items-center space-x-3">
              <HelpCircle className="w-6 h-6 text-[#00ff88]" />
              <h2 className="text-lg font-bold font-mono uppercase tracking-wider">
                Keyboard Shortcuts Cheat Sheet
              </h2>
            </div>

            <div className="space-y-3 font-mono text-xs">
              <div className="flex justify-between py-1.5 border-b border-zinc-900">
                <span className="text-zinc-400">Toggle Triage / Management</span>
                <span className="text-[#00ff88] font-bold">Tab / 1 / 2</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-zinc-900">
                <span className="text-zinc-400">Select Card (Triage)</span>
                <span className="text-zinc-200 font-bold">Single-Click</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-zinc-900">
                <span className="text-zinc-400">Purchase / Open Listing (Buy)</span>
                <span className="text-[#00ff88] font-bold">W / Double-Click / Swipe Right</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-zinc-900">
                <span className="text-zinc-400">Archive Listing</span>
                <span className="text-red-400 font-bold">S / Right-Click / Swipe Left</span>
              </div>
              <div className="flex justify-between py-1.5 border-b border-zinc-900">
                <span className="text-zinc-400">Cycle Images (Non-looping)</span>
                <span className="text-zinc-200 font-bold">Mouse Wheel / Touch Swipe</span>
              </div>
              <div className="flex justify-between py-1.5">
                <span className="text-zinc-400">Toggle Cheat Sheet</span>
                <span className="text-[#00ff88] font-bold">?</span>
              </div>
            </div>

            <div className="pt-2 text-right">
              <button
                onClick={() => setIsCheatSheetOpen(false)}
                className="px-4 py-2 bg-[#00ff88] text-black font-mono font-bold uppercase text-xs hover:bg-[#4ade80]"
              >
                Close (ESC / ?)
              </button>
            </div>
          </div>
        </div>
      )}

      {/* OLED Brutalist Header */}
      <header className="sticky top-0 z-40 bg-[#000000]/90 border-b border-zinc-900 shadow-md backdrop-blur-md px-6 py-4">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Brand & Status Indicator */}
          <div className="flex items-center space-x-4">
            <div className="p-2.5 bg-[#00ff88] text-black rounded-none">
              <Camera className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center space-x-3">
                <h1 className="text-lg font-bold tracking-tight text-white uppercase font-mono">
                  Y2K Arbitrage Command Center
                </h1>
                <div className="flex items-center space-x-2">
                  <span
                    className={`w-2.5 h-2.5 rounded-full ${
                      isScanning ? "bg-amber-400 animate-ping" : "bg-[#00ff88]"
                    }`}
                  />
                  <span className="text-[10px] font-mono font-bold uppercase text-zinc-400">
                    {isScanning ? `SCANNING (${scanType})` : "IDLE"}
                  </span>
                </div>
              </div>
              <div className="flex items-center space-x-4 text-xs text-zinc-400 mt-0.5 font-mono">
                <span>Pending: <strong className="text-white">{pendingItems.length}</strong></span>
                <span>/</span>
                <span>Last Scan: {lastScanTime}</span>
                <span>/</span>
                <span
                  className={
                    isSupabaseConnected ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"
                  }
                >
                  {isSupabaseConnected ? "Supabase Live" : "Offline Cache"}
                </span>
              </div>
            </div>
          </div>

          {/* Header Action Buttons & Mode Switcher */}
          <div className="flex items-center space-x-3">
            <button
              onClick={() => handleTriggerScan("fast")}
              disabled={isScanning}
              className="flex items-center px-3 py-2 bg-blue-900/30 border border-blue-500/50 hover:bg-blue-800/40 text-blue-400 font-mono text-xs font-bold uppercase tracking-wider transition-colors"
              title="Trigger Fast-Track scan (Exact match 10m)"
            >
              <Zap className="w-3.5 h-3.5 mr-1.5 text-blue-400" />
              Fast Scan (10m)
            </button>

            <button
              onClick={() => handleTriggerScan("slow")}
              disabled={isScanning}
              className="flex items-center px-3 py-2 bg-purple-900/30 border border-purple-500/50 hover:bg-purple-800/40 text-purple-400 font-mono text-xs font-bold uppercase tracking-wider transition-colors"
              title="Trigger Slow-Track scan (Generic VLM 60m)"
            >
              <Activity className="w-3.5 h-3.5 mr-1.5 text-purple-400" />
              Slow Scan (60m)
            </button>

            <button
              onClick={handlePurgeListings}
              disabled={isScanning}
              className="flex items-center px-3 py-2 bg-red-950/30 border border-red-800/50 hover:bg-red-900/40 text-red-400 font-mono text-xs font-bold uppercase tracking-wider transition-colors"
              title="Purge all listings and restart fresh VLM scan feed"
            >
              <Trash2 className="w-3.5 h-3.5 mr-1.5 text-red-400" />
              Reset Feed
            </button>

            <button
              onClick={() => setIsCheatSheetOpen(true)}
              className="p-2 border border-zinc-800 hover:border-zinc-700 bg-zinc-950 text-zinc-300 transition-colors"
              title="Keyboard Cheat Sheet (?)"
            >
              <HelpCircle className="w-4 h-4" />
            </button>

            <div className="flex items-center bg-zinc-950 p-1 border border-zinc-800">
              <button
                onClick={() => setMode("triage")}
                className={`flex items-center px-3.5 py-1.5 text-xs font-bold uppercase tracking-wider transition-all duration-150 ${
                  mode === "triage"
                    ? "bg-[#00ff88] text-black shadow-sm"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <Grid className="w-3.5 h-3.5 mr-1.5" />
                Triage ({pendingItems.length}) (1)
              </button>
              <button
                onClick={() => setMode("wanted")}
                className={`flex items-center px-3.5 py-1.5 text-xs font-bold uppercase tracking-wider transition-all duration-150 ${
                  mode === "wanted"
                    ? "bg-[#00ff88] text-black shadow-sm"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <Sparkles className="w-3.5 h-3.5 mr-1.5 text-[#00ff88]" />
                I Want It List ({wantedItems.length}) (2)
              </button>
              <button
                onClick={() => setMode("management")}
                className={`flex items-center px-3.5 py-1.5 text-xs font-bold uppercase tracking-wider transition-all duration-150 ${
                  mode === "management"
                    ? "bg-[#00ff88] text-black shadow-sm"
                    : "text-zinc-400 hover:text-white"
                }`}
              >
                <Table className="w-3.5 h-3.5 mr-1.5" />
                Management ({items.length}) (3)
              </button>
            </div>
          </div>
        </div>

        {/* Stats Summary Bar */}
        <div className="max-w-7xl mx-auto mt-4 pt-3 border-t border-zinc-900 grid grid-cols-2 sm:grid-cols-5 gap-4 font-mono text-xs text-zinc-400">
          <div>
            <span className="block text-[10px] text-zinc-500 uppercase">Total Listings</span>
            <span className="text-sm font-bold text-white">{totalListings}</span>
          </div>
          <div>
            <span className="block text-[10px] text-zinc-500 uppercase">Profitable Deallist</span>
            <span className="text-sm font-bold text-[#00ff88]">{profitableCount}</span>
          </div>
          <div>
            <span className="block text-[10px] text-zinc-500 uppercase">Avg Margin</span>
            <span className="text-sm font-bold text-emerald-400">+{avgMargin.toFixed(1)}%</span>
          </div>
          <div>
            <span className="block text-[10px] text-zinc-500 uppercase">Potential Profit</span>
            <span className="text-sm font-bold text-[#00ff88]">+${totalPotentialProfit.toFixed(2)}</span>
          </div>
          <div>
            <span className="block text-[10px] text-zinc-500 uppercase">Sources (Exact / Generic)</span>
            <span className="text-sm font-bold text-zinc-200">
              <span className="text-blue-400">{exactCount}</span> / <span className="text-purple-400">{genericCount}</span>
            </span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="max-w-7xl mx-auto px-6 py-6">
        {mode === "triage" ? (
          <div>
            {/* Triage Grid */}
            {pendingItems.length === 0 ? (
              <div className="text-center py-28 border border-zinc-900 bg-zinc-950">
                <CheckCircle2 className="w-12 h-12 text-[#00ff88] mx-auto mb-3" />
                <h3 className="text-base font-bold uppercase tracking-wider text-white font-mono">
                  All Pending Listings Triaged!
                </h3>
                <p className="text-xs text-zinc-400 mt-1 font-mono">
                  No active pending deals. Check your "I Want It" list, trigger a Fast/Slow Scan, or switch to Management Mode.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 items-start">
                {pendingItems.map((item) => (
                  <OledMasonryCard
                    key={item.id}
                    item={item}
                    isSelected={selectedCardId === item.id}
                    isAnimating={animatingCardId?.id === item.id ? animatingCardId.action : null}
                    onSelect={() => setSelectedCardId(item.id)}
                    onWorthy={() => handleWorthy(item)}
                    onUnworthy={() => handleUnworthy(item)}
                    onOpenModal={() => setDetailModalItem(item)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : mode === "wanted" ? (
          <div>
            <div className="flex items-center justify-between mb-4 border-b border-zinc-900 pb-3 font-mono">
              <h2 className="text-sm font-bold uppercase tracking-wider text-[#00ff88] flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-[#00ff88]" />
                I Want It List — Saved Camera Deals ({wantedItems.length})
              </h2>
              <span className="text-xs text-zinc-400">
                Double-click or press W in Triage mode adds items here.
              </span>
            </div>
            {wantedItems.length === 0 ? (
              <div className="text-center py-28 border border-zinc-900 bg-zinc-950">
                <Sparkles className="w-12 h-12 text-zinc-600 mx-auto mb-3" />
                <h3 className="text-base font-bold uppercase tracking-wider text-white font-mono">
                  No Saved Deals Yet!
                </h3>
                <p className="text-xs text-zinc-400 mt-1 font-mono">
                  Double-click or press W on any camera card in Triage mode to add it to your "I Want It" list.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 items-start">
                {wantedItems.map((item) => (
                  <OledMasonryCard
                    key={item.id}
                    item={item}
                    isSelected={selectedCardId === item.id}
                    isAnimating={animatingCardId?.id === item.id ? animatingCardId.action : null}
                    onSelect={() => setSelectedCardId(item.id)}
                    onWorthy={() => window.open(item.ebay_url, "_blank")}
                    onUnworthy={() => handleUnworthy(item)}
                    onOpenModal={() => setDetailModalItem(item)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          /* Management Mode TanStack Data Table */
          <div className="space-y-4">
            {/* Table Filters & Tools */}
            <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-zinc-950 p-4 border border-zinc-900 font-mono text-xs">
              <div className="flex items-center space-x-3">
                <Filter className="w-4 h-4 text-zinc-400" />
                <select
                  value={sourceFilter}
                  onChange={(e) => setSourceFilter(e.target.value)}
                  className="bg-black border border-zinc-800 text-xs text-white px-3 py-1.5 focus:outline-none focus:border-[#00ff88]"
                >
                  <option value="all">All Sources</option>
                  <option value="Exact Match">Exact Match</option>
                  <option value="Generic VLM">Generic VLM</option>
                </select>

                <select
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  className="bg-black border border-zinc-800 text-xs text-white px-3 py-1.5 focus:outline-none focus:border-[#00ff88]"
                >
                  <option value="all">All Statuses</option>
                  <option value="pending">Pending</option>
                  <option value="purchased">Purchased</option>
                  <option value="in_transit">In Transit</option>
                  <option value="testing">Testing</option>
                  <option value="relisted">Relisted</option>
                  <option value="sold">Sold</option>
                  <option value="archived">Archived</option>
                </select>
              </div>

              <div className="flex items-center space-x-3">
                <button
                  onClick={handleDeduplicate}
                  className="flex items-center text-[#00ff88] hover:underline font-bold"
                >
                  <CopyX className="w-3.5 h-3.5 mr-1" /> Deduplicate
                </button>
                <span className="text-zinc-500">
                  Showing {table.getRowModel().rows.length} of {items.length} records
                </span>
              </div>
            </div>

            {/* Sticky Bottom Floating Bulk Action Bar */}
            {selectedRows.length > 0 && (
              <div className="sticky bottom-6 z-50 bg-zinc-900 border border-zinc-700 text-white p-4 shadow-2xl flex items-center justify-between font-mono text-xs max-w-4xl mx-auto">
                <div className="flex items-center space-x-3">
                  <CheckSquare className="w-4 h-4 text-[#00ff88]" />
                  <span className="font-bold">{selectedRows.length} item(s) selected</span>
                </div>

                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleBulkStatusChange("in_transit")}
                    className="px-3 py-1.5 bg-amber-600/30 text-amber-400 border border-amber-500/50 hover:bg-amber-600/50 font-bold uppercase text-[11px]"
                  >
                    In Transit
                  </button>
                  <button
                    onClick={() => handleBulkStatusChange("testing")}
                    className="px-3 py-1.5 bg-cyan-600/30 text-cyan-400 border border-cyan-500/50 hover:bg-cyan-600/50 font-bold uppercase text-[11px]"
                  >
                    Testing
                  </button>
                  <button
                    onClick={() => handleBulkStatusChange("relisted")}
                    className="px-3 py-1.5 bg-blue-600/30 text-blue-400 border border-blue-500/50 hover:bg-blue-600/50 font-bold uppercase text-[11px]"
                  >
                    Relisted
                  </button>
                  <button
                    onClick={() => handleBulkStatusChange("sold")}
                    className="px-3 py-1.5 bg-purple-600/30 text-purple-400 border border-purple-500/50 hover:bg-purple-600/50 font-bold uppercase text-[11px]"
                  >
                    Sold
                  </button>
                  <button
                    onClick={() => handleBulkStatusChange("archived")}
                    className="px-3 py-1.5 bg-zinc-800 text-zinc-300 border border-zinc-700 hover:bg-zinc-700 font-bold uppercase text-[11px]"
                  >
                    Archive
                  </button>
                  <button
                    onClick={handleBulkDelete}
                    className="px-3 py-1.5 bg-red-600 text-white hover:bg-red-700 font-bold uppercase text-[11px]"
                  >
                    Delete
                  </button>
                </div>
              </div>
            )}

            {/* TanStack Table Container */}
            <div className="border border-zinc-900 bg-zinc-950 overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-zinc-200 border-collapse">
                  <thead className="bg-zinc-900 text-zinc-400 uppercase font-mono text-[11px] font-bold border-b border-zinc-800">
                    {table.getHeaderGroups().map((headerGroup) => (
                      <tr key={headerGroup.id}>
                        {headerGroup.headers.map((header) => (
                          <th key={header.id} className="p-3.5">
                            {header.isPlaceholder
                              ? null
                              : flexRender(header.column.columnDef.header, header.getContext())}
                          </th>
                        ))}
                      </tr>
                    ))}
                  </thead>
                  <tbody className="divide-y divide-zinc-900 font-sans">
                    {table.getRowModel().rows.length === 0 ? (
                      <tr>
                        <td colSpan={columns.length} className="p-12 text-center text-zinc-500 font-mono">
                          No matching listings found.
                        </td>
                      </tr>
                    ) : (
                      table.getRowModel().rows.map((row) => {
                        const isExpanded = expandedRowId === row.original.id;
                        return (
                          <React.Fragment key={row.id}>
                            <tr
                              className={`hover:bg-zinc-900/50 transition-colors ${
                                row.getIsSelected() ? "bg-zinc-900" : ""
                              }`}
                            >
                              {row.getVisibleCells().map((cell) => (
                                <td key={cell.id} className="p-3.5">
                                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                                </td>
                              ))}
                            </tr>
                            {isExpanded && (
                              <tr className="bg-zinc-950 border-b border-zinc-900">
                                <td colSpan={columns.length} className="p-6 font-mono text-xs">
                                  <div className="space-y-4 max-w-4xl">
                                    <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
                                      <h4 className="text-sm font-bold text-white">
                                        {row.original.model_name} Details & Gallery
                                      </h4>
                                      <span className="text-zinc-400 text-xs">ID: {row.original.id}</span>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                      <div>
                                        <span className="block text-zinc-500 text-[10px] uppercase">
                                          Damage & Condition Notes:
                                        </span>
                                        <p className="text-zinc-200 mt-1 italic">
                                          "{row.original.damage_notes}"
                                        </p>
                                      </div>
                                      <div>
                                        <span className="block text-zinc-500 text-[10px] uppercase">
                                          Confidence & Source:
                                        </span>
                                        <p className="text-zinc-200 mt-1">
                                          Source: {row.original.pipeline_source} | Confidence: {(row.original.confidence_score * 100).toFixed(0)}%
                                        </p>
                                      </div>
                                    </div>
                                    <div>
                                      <span className="block text-zinc-500 text-[10px] uppercase mb-2">
                                        All Scraped Images ({row.original.image_urls.length}):
                                      </span>
                                      <div className="flex items-center space-x-3 overflow-x-auto pb-2">
                                        {row.original.image_urls.map((imgUrl, idx) => (
                                          <img
                                            key={idx}
                                            src={imgUrl}
                                            alt=""
                                            className="w-24 h-24 object-cover border border-zinc-800 rounded-none flex-shrink-0"
                                          />
                                        ))}
                                      </div>
                                    </div>
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
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

      {/* Detail Modal for Mobile / Tap action */}
      {detailModalItem && (
        <div className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-zinc-950 border border-zinc-800 text-white max-w-lg w-full p-6 space-y-4 relative font-mono">
            <button
              onClick={() => setDetailModalItem(null)}
              className="absolute top-4 right-4 text-zinc-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            <h3 className="text-base font-bold text-white">{detailModalItem.model_name}</h3>
            <img
              src={detailModalItem.image_urls[0]}
              alt=""
              className="w-full h-64 object-contain bg-black border border-zinc-800"
            />
            <div className="grid grid-cols-2 gap-4 bg-zinc-900 p-3 border border-zinc-800">
              <div>
                <span className="text-[10px] text-zinc-400 block uppercase">Asking</span>
                <span className="text-lg font-bold">${detailModalItem.asking_price.toFixed(2)}</span>
              </div>
              <div>
                <span className="text-[10px] text-zinc-400 block uppercase">Market Value</span>
                <span className="text-lg font-bold text-[#00ff88]">${detailModalItem.market_value.toFixed(2)}</span>
              </div>
            </div>
            <p className="text-xs text-zinc-300 italic">"{detailModalItem.damage_notes}"</p>
            <div className="flex space-x-3 pt-2">
              <button
                onClick={() => {
                  handleWorthy(detailModalItem);
                  setDetailModalItem(null);
                }}
                className="flex-1 py-2.5 bg-[#00ff88] text-black font-bold uppercase text-xs"
              >
                Buy Now [W]
              </button>
              <button
                onClick={() => {
                  handleUnworthy(detailModalItem);
                  setDetailModalItem(null);
                }}
                className="flex-1 py-2.5 bg-red-600/30 text-red-400 border border-red-500/50 font-bold uppercase text-xs"
              >
                Archive [S]
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

{/* OLED Brutalist Masonry Card */}
function OledMasonryCard({
  item,
  isSelected,
  isAnimating,
  onSelect,
  onWorthy,
  onUnworthy,
  onOpenModal,
}: {
  item: ArbitrageItem;
  isSelected: boolean;
  isAnimating: "purchase" | "archive" | null;
  onSelect: () => void;
  onWorthy: () => void;
  onUnworthy: () => void;
  onOpenModal: () => void;
}) {
  const [imgIdx, setImgIdx] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  // Non-passive wheel event listener with hard stop at last image
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      if (e.deltaY > 0) {
        setImgIdx((prev) => Math.min(item.image_urls.length - 1, prev + 1));
      } else if (e.deltaY < 0) {
        setImgIdx((prev) => Math.max(0, prev - 1));
      }
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [item.image_urls.length]);

  // Mobile Touch Tinder Swipe handlers
  const handleTouchStart = (e: React.TouchEvent) => {
    const touch = e.touches[0];
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    if (!touchStartRef.current) return;
    const touch = e.changedTouches[0];
    const deltaX = touch.clientX - touchStartRef.current.x;
    const deltaY = touch.clientY - touchStartRef.current.y;

    if (Math.abs(deltaX) > 100 && Math.abs(deltaX) > Math.abs(deltaY)) {
      if (deltaX > 0) {
        onWorthy();
      } else {
        onUnworthy();
      }
    } else if (Math.abs(deltaX) < 10 && Math.abs(deltaY) < 10) {
      onOpenModal();
    }
    touchStartRef.current = null;
  };

  let animationClass = "";
  if (isAnimating === "purchase") {
    animationClass = "ring-4 ring-[#00ff88] scale-0 duration-300";
  } else if (isAnimating === "archive") {
    animationClass = "ring-4 ring-[#ff4444] scale-0 duration-300";
  }

  let marginColor = "text-zinc-200";
  if (item.profit_margin > 40) marginColor = "text-[#00ff88]";
  else if (item.profit_margin >= 25) marginColor = "text-[#4ade80]";
  else if (item.profit_margin < 0) marginColor = "text-[#ff4444]";

  return (
    <div
      ref={cardRef}
      onClick={() => onSelect()}
      onDoubleClick={onWorthy}
      onContextMenu={(e) => {
        e.preventDefault();
        onUnworthy();
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      className={`relative w-full rounded-none overflow-hidden cursor-pointer select-none bg-zinc-950 border transition-all duration-150 ${
        isSelected ? "ring-2 ring-[#00ff88] border-[#00ff88]" : "border-zinc-800 hover:border-zinc-700"
      } ${animationClass}`}
    >
      {/* Aspect Ratio Native Image (no cropping) */}
      <div className="relative w-full bg-black min-h-[260px] flex items-center justify-center">
        <img
          src={item.image_urls[imgIdx]}
          alt={item.model_name}
          className="w-full h-auto max-h-[340px] object-contain transition-transform duration-150"
        />

        {/* Dot Indicators */}
        {item.image_urls.length > 1 && (
          <div className="absolute bottom-2 left-1/2 -translate-x-1/2 flex items-center space-x-1 font-mono text-[10px] text-zinc-400 bg-black/60 px-2 py-0.5 rounded-full backdrop-blur-sm">
            {item.image_urls.map((_, i) => (
              <span key={i} className={i === imgIdx ? "text-[#00ff88]" : "text-zinc-600"}>
                {i === imgIdx ? "●" : "○"}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Non-Hover Card Information Footer */}
      <div className="p-4 space-y-2 bg-zinc-950 border-t border-zinc-900">
        <div className="flex items-start justify-between gap-2">
          <h3 className="font-bold text-xs text-white line-clamp-1 font-mono">
            {item.model_name}
          </h3>
          <span className={`text-xs font-extrabold font-mono flex-shrink-0 ${marginColor}`}>
            +{item.profit_margin.toFixed(0)}%
          </span>
        </div>
        <div className="flex items-center justify-between text-[11px] text-zinc-400 font-mono">
          <span>${item.asking_price.toFixed(2)} asking</span>
          <span className="text-emerald-400">${item.market_value.toFixed(2)} market</span>
        </div>
      </div>

      {/* Hover Card Backdrop Blur (150ms transition) Overlay */}
      {isHovered && (
        <div className="absolute inset-0 bg-black/90 backdrop-blur-xl p-5 flex flex-col justify-between transition-all duration-150 border border-[#00ff88] font-mono text-xs">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span
                className={
                  item.pipeline_source === "Exact Match"
                    ? "bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded-full px-2.5 py-0.5 text-[10px]"
                    : "bg-purple-600/20 text-purple-400 border border-purple-500/30 rounded-full px-2.5 py-0.5 text-[10px]"
                }
              >
                {item.pipeline_source}
              </span>
              <span className="text-[10px] text-zinc-400">
                Photo {imgIdx + 1}/{item.image_urls.length}
              </span>
            </div>
            <h3 className="font-bold text-xs text-white line-clamp-2">{item.model_name}</h3>
          </div>

          <div className="grid grid-cols-2 gap-2 bg-zinc-900 p-2 border border-zinc-800">
            <div>
              <span className="text-[9px] text-zinc-500 uppercase block">Asking</span>
              <span className="text-sm font-bold text-white">${item.asking_price.toFixed(2)}</span>
            </div>
            <div>
              <span className="text-[9px] text-zinc-500 uppercase block">Market</span>
              <span className="text-sm font-bold text-[#00ff88]">${item.market_value.toFixed(2)}</span>
            </div>
          </div>

          <div className="space-y-1 bg-zinc-900 p-2 border border-zinc-800">
            <div className="flex justify-between text-[10px]">
              <span className="text-zinc-400">Damage:</span>
              <span className={item.damage_severity === "None" ? "text-emerald-400 font-bold" : "text-amber-400 font-bold"}>
                {item.damage_severity}
              </span>
            </div>
            <p className="text-[10px] text-zinc-300 italic line-clamp-2">"{item.damage_notes}"</p>
          </div>

          <div className="flex justify-between text-[10px] pt-1 border-t border-zinc-800 font-bold">
            <span className="text-[#00ff88]">[W] / Dbl-Click: Buy</span>
            <span className="text-red-400">[S] / Right-Click: Archive</span>
          </div>
        </div>
      )}
    </div>
  );
}
