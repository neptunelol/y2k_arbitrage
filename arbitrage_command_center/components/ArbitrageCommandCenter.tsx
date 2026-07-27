"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  ColumnDef,
  SortingState,
  RowSelectionState,
  flexRender,
} from "@tanstack/react-table";
import {
  LayoutGrid,
  Table as TableIcon,
  Zap,
  ShieldCheck,
  RefreshCw,
  Search,
  Filter,
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  Trash2,
  Archive,
  ShoppingBag,
  Truck,
  RotateCcw,
  ExternalLink,
  AlertTriangle,
  CheckCircle2,
  Eye,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// --- Types & Data Contracts ---

export type DamageSeverity = "none" | "minor" | "major";
export type ItemStatus = "active" | "purchased" | "in_transit" | "relisted" | "archived";
export type SourceBadgeType = "Generic VLM" | "Exact Match";

export interface ArbitrageItem {
  id: string;
  listing_url: string;
  title: string;
  identified_model: string;
  asking_price: number;
  market_value: number | null;
  profit_margin: number | null; // percentage e.g. 75.0 for 75%
  is_profitable_deal: boolean;
  confidence_score: number; // 0.0 to 1.0
  damage_severity: DamageSeverity;
  damage_notes: string;
  image_urls: string[];
  source_badge: SourceBadgeType;
  status: ItemStatus;
  created_at: string;
}

// --- Rich Mock Dataset (10+ Camera Listings) ---

export const INITIAL_DATASET: ArbitrageItem[] = [
  {
    id: "cam-001",
    listing_url: "https://www.ebay.com/itm/123456789012",
    title: "Sony Cyber-shot DSC-T700 Silver 10.1MP Digital Camera Estate Sale",
    identified_model: "Sony Cyber-shot DSC-T700",
    asking_price: 35.0,
    market_value: 140.0,
    profit_margin: 75.0,
    is_profitable_deal: true,
    confidence_score: 0.95,
    damage_severity: "minor",
    damage_notes: "Minor surface scuffs on corner metal trim; screen clear and responsive",
    image_urls: [
      "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1512790182412-b19e6d62bc39?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "active",
    created_at: "2026-07-26T20:30:00Z",
  },
  {
    id: "cam-002",
    listing_url: "https://www.ebay.com/itm/123456789013",
    title: "Vintage Canon IXY Digital 50 / PowerShot SD400 Silver Point & Shoot",
    identified_model: "Canon PowerShot SD400",
    asking_price: 28.5,
    market_value: 85.0,
    profit_margin: 66.47,
    is_profitable_deal: true,
    confidence_score: 0.89,
    damage_severity: "none",
    damage_notes: "Clean body, light lens barrel wear, fully functional lens door",
    image_urls: [
      "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "active",
    created_at: "2026-07-26T20:45:00Z",
  },
  {
    id: "cam-003",
    listing_url: "https://www.ebay.com/itm/123456789014",
    title: "Nikon Coolpix S210 Pink Compact Camera Untested Lot",
    identified_model: "Nikon Coolpix S210",
    asking_price: 42.0,
    market_value: 60.0,
    profit_margin: 30.0,
    is_profitable_deal: false,
    confidence_score: 0.92,
    damage_severity: "minor",
    damage_notes: "Battery cover latch slightly loose, minor bezel scratches",
    image_urls: [
      "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Generic VLM",
    status: "active",
    created_at: "2026-07-26T21:00:00Z",
  },
  {
    id: "cam-004",
    listing_url: "https://www.ebay.com/itm/123456789015",
    title: "Olympus Stylus Verve Digital 4.0MP Red Y2K Estate Sale Camera",
    identified_model: "Olympus Stylus Verve Digital",
    asking_price: 19.99,
    market_value: 95.0,
    profit_margin: 78.96,
    is_profitable_deal: true,
    confidence_score: 0.94,
    damage_severity: "none",
    damage_notes: "Mint condition, original wrist strap included",
    image_urls: [
      "https://images.unsplash.com/photo-1564466809058-bf4114d55352?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "active",
    created_at: "2026-07-26T21:10:00Z",
  },
  {
    id: "cam-005",
    listing_url: "https://www.ebay.com/itm/123456789016",
    title: "Fujifilm FinePix Z1 Silver 5.1MP Cracked LCD Screen",
    identified_model: "Fujifilm FinePix Z1",
    asking_price: 15.0,
    market_value: null,
    profit_margin: null,
    is_profitable_deal: false,
    confidence_score: 0.91,
    damage_severity: "major",
    damage_notes: "Cracked LCD glass display and spiderweb fracture across screen",
    image_urls: [
      "https://images.unsplash.com/photo-1512790182412-b19e6d62bc39?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "archived",
    created_at: "2026-07-26T21:15:00Z",
  },
  {
    id: "cam-006",
    listing_url: "https://www.ebay.com/itm/123456789017",
    title: "Casio Exilim EX-S500 Card Camera Ultra Slim Silver",
    identified_model: "Casio Exilim EX-S500",
    asking_price: 24.99,
    market_value: 110.0,
    profit_margin: 77.28,
    is_profitable_deal: true,
    confidence_score: 0.88,
    damage_severity: "none",
    damage_notes: "Tested working, pristine optical glass",
    image_urls: [
      "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Generic VLM",
    status: "active",
    created_at: "2026-07-26T21:20:00Z",
  },
  {
    id: "cam-007",
    listing_url: "https://www.ebay.com/itm/123456789018",
    title: "Sony Cyber-shot DSC-W55 Blue 7.2MP Digital Camera",
    identified_model: "Sony Cyber-shot DSC-W55",
    asking_price: 32.0,
    market_value: 90.0,
    profit_margin: 64.44,
    is_profitable_deal: true,
    confidence_score: 0.96,
    damage_severity: "minor",
    damage_notes: "Small ding on top right metal shell edge",
    image_urls: [
      "https://images.unsplash.com/photo-1510127034890-ba27508e9f1c?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1564466809058-bf4114d55352?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "purchased",
    created_at: "2026-07-26T21:25:00Z",
  },
  {
    id: "cam-008",
    listing_url: "https://www.ebay.com/itm/123456789019",
    title: "Panasonic Lumix DMC-FX01 Ultra Compact Wide Lens",
    identified_model: "Panasonic Lumix DMC-FX01",
    asking_price: 22.0,
    market_value: 80.0,
    profit_margin: 72.5,
    is_profitable_deal: true,
    confidence_score: 0.87,
    damage_severity: "none",
    damage_notes: "Clean sensor, works perfectly",
    image_urls: [
      "https://images.unsplash.com/photo-1502920917128-1aa500764cbd?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Generic VLM",
    status: "in_transit",
    created_at: "2026-07-26T21:30:00Z",
  },
  {
    id: "cam-009",
    listing_url: "https://www.ebay.com/itm/123456789020",
    title: "Fujifilm FinePix F30 High ISO King Compact CCD",
    identified_model: "Fujifilm FinePix F30",
    asking_price: 55.0,
    market_value: 165.0,
    profit_margin: 66.67,
    is_profitable_deal: true,
    confidence_score: 0.93,
    damage_severity: "minor",
    damage_notes: "Minor battery door rubber port seal missing",
    image_urls: [
      "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=600&auto=format&fit=crop&q=80",
      "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "relisted",
    created_at: "2026-07-26T21:35:00Z",
  },
  {
    id: "cam-010",
    listing_url: "https://www.ebay.com/itm/123456789021",
    title: "Canon PowerShot A540 6.0MP Digital Camera Untested",
    identified_model: "Canon PowerShot A540",
    asking_price: 18.5,
    market_value: 52.0,
    profit_margin: 64.42,
    is_profitable_deal: true,
    confidence_score: 0.9,
    damage_severity: "none",
    damage_notes: "Uses AA batteries; clean compartment",
    image_urls: [
      "https://images.unsplash.com/photo-1564466809058-bf4114d55352?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Exact Match",
    status: "active",
    created_at: "2026-07-26T21:40:00Z",
  },
  {
    id: "cam-011",
    listing_url: "https://www.ebay.com/itm/123456789022",
    title: "Old Silver Digicam Estate Sale Lot - Unbranded Body",
    identified_model: "Unknown Digicam Model",
    asking_price: 45.0,
    market_value: null,
    profit_margin: null,
    is_profitable_deal: false,
    confidence_score: 0.42,
    damage_severity: "major",
    damage_notes: "Corroded battery terminals and stuck optical zoom lens assembly",
    image_urls: [
      "https://images.unsplash.com/photo-1512790182412-b19e6d62bc39?w=600&auto=format&fit=crop&q=80",
    ],
    source_badge: "Generic VLM",
    status: "active",
    created_at: "2026-07-26T21:45:00Z",
  },
];

// --- Pre-loader Hook for Fast Zero-Latency Triage Queue ---

function usePrefetchTriageQueue(items: ArbitrageItem[], activeIndex: number) {
  useEffect(() => {
    if (!items.length) return;
    const queue = items.slice(activeIndex, activeIndex + 4);
    queue.forEach((item) => {
      // 1. Preload image objects into browser memory
      item.image_urls.forEach((url) => {
        const img = new Image();
        img.src = url;
      });

      // 2. Inject prefetch link tag into head for target URL
      if (item.listing_url && typeof document !== "undefined") {
        const existingLink = document.querySelector(
          `link[rel="prefetch"][href="${item.listing_url}"]`
        );
        if (!existingLink) {
          const link = document.createElement("link");
          link.rel = "prefetch";
          link.href = item.listing_url;
          link.as = "document";
          document.head.appendChild(link);
        }
      }
    });
  }, [items, activeIndex]);
}

// --- Individual Triage Hover Card Component ---

interface TriageCardProps {
  item: ArbitrageItem;
  isActive: boolean;
  onSelect: () => void;
  onPurchase: () => void;
  onArchive: () => void;
}

function TriageCard({
  item,
  isActive,
  onSelect,
  onPurchase,
  onArchive,
}: TriageCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [currentImageIndex, setCurrentImageIndex] = useState(0);

  // Non-passive wheel event listener to handle carousel cycling without page scroll jitter
  useEffect(() => {
    const cardEl = cardRef.current;
    if (!cardEl) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault(); // Suppress window scroll
      if (item.image_urls.length <= 1) return;

      if (e.deltaY > 0) {
        // Scroll down -> Next image
        setCurrentImageIndex((prev) => (prev + 1) % item.image_urls.length);
      } else if (e.deltaY < 0) {
        // Scroll up -> Prev image
        setCurrentImageIndex(
          (prev) => (prev - 1 + item.image_urls.length) % item.image_urls.length
        );
      }
    };

    // MUST use { passive: false } to allow e.preventDefault()
    cardEl.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      cardEl.removeEventListener("wheel", handleWheel);
    };
  }, [item.image_urls.length]);

  const activeImageUrl =
    item.image_urls[currentImageIndex] ||
    item.image_urls[0] ||
    "/placeholder-camera.jpg";

  const isHighProfit = item.profit_margin !== null && item.profit_margin >= 40;

  return (
    <div
      ref={cardRef}
      onClick={onSelect}
      onContextMenu={(e) => {
        e.preventDefault(); // Suppress context menu
        onArchive();
      }}
      className={cn(
        "group relative flex flex-col h-80 rounded-xl overflow-hidden shadow-md bg-slate-900 border border-slate-800 transition-all duration-200 cursor-pointer select-none",
        isActive
          ? "ring-2 ring-blue-500 border-transparent scale-[1.02] shadow-xl shadow-blue-950/40 z-10"
          : "hover:border-slate-700 hover:shadow-lg"
      )}
    >
      {/* Primary Card Background Image */}
      <div className="relative w-full h-full bg-slate-950 overflow-hidden">
        <img
          src={activeImageUrl}
          alt={item.identified_model}
          className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
        />

        {/* Gradient Overlay at Bottom */}
        <div className="absolute inset-x-0 bottom-0 h-36 bg-gradient-to-t from-slate-950 via-slate-950/70 to-transparent flex flex-col justify-end p-4 z-0 pointer-events-none" />

        {/* Top Badges overlay on Card Base */}
        <div className="absolute top-2 left-2 right-2 flex items-center justify-between gap-1 z-10">
          <Badge
            variant={item.source_badge === "Exact Match" ? "cyan" : "secondary"}
            className="text-[10px] uppercase font-mono tracking-wider shadow-sm"
          >
            {item.source_badge}
          </Badge>
          {isHighProfit && (
            <Badge variant="success" className="font-bold text-xs shadow-md">
              +{item.profit_margin?.toFixed(0)}% Margin
            </Badge>
          )}
        </div>

        {/* Carousel Image Indicator Dots */}
        {item.image_urls.length > 1 && (
          <div className="absolute top-2.5 right-2 z-10 flex gap-1 bg-slate-950/60 backdrop-blur-sm px-2 py-1 rounded-full border border-slate-800/60">
            {item.image_urls.map((_, idx) => (
              <div
                key={idx}
                className={cn(
                  "h-1.5 rounded-full transition-all duration-200",
                  idx === currentImageIndex ? "w-3.5 bg-blue-400" : "w-1.5 bg-slate-600/70"
                )}
              />
            ))}
          </div>
        )}

        {/* Base Card Bottom Title & Asking Price */}
        <div className="absolute bottom-3 left-4 right-4 z-0 group-hover:opacity-0 transition-opacity duration-200">
          <h3 className="font-bold text-white text-sm truncate">{item.identified_model}</h3>
          <div className="flex items-center justify-between text-xs text-slate-300 mt-1">
            <span>
              Ask: <strong className="text-emerald-400 font-mono">${item.asking_price.toFixed(2)}</strong>
            </span>
            <span>
              Est: <strong className="font-mono">{item.market_value !== null ? `$${item.market_value.toFixed(2)}` : "N/A"}</strong>
            </span>
          </div>
        </div>

        {/* Hover Deep Dive Overlay with Backdrop Blur */}
        <div className="absolute inset-0 bg-slate-950/85 backdrop-blur-md p-4 opacity-0 group-hover:opacity-100 transition-opacity duration-200 z-20 flex flex-col justify-between pointer-events-auto">
          {/* Header Badges */}
          <div className="flex items-center justify-between gap-2">
            <span
              className={cn(
                "text-[10px] font-mono font-semibold px-2 py-0.5 rounded border uppercase tracking-wider",
                item.source_badge === "Exact Match"
                  ? "bg-sky-500/20 text-sky-300 border-sky-500/30"
                  : "bg-purple-500/20 text-purple-300 border-purple-500/30"
              )}
            >
              {item.source_badge}
            </span>
            <span
              className={cn(
                "text-[10px] font-semibold px-2 py-0.5 rounded border flex items-center gap-1 uppercase",
                item.damage_severity === "none" && "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
                item.damage_severity === "minor" && "bg-amber-500/20 text-amber-300 border-amber-500/30",
                item.damage_severity === "major" && "bg-rose-500/20 text-rose-300 border-rose-500/30"
              )}
            >
              {item.damage_severity} Damage
            </span>
          </div>

          {/* Model Title */}
          <div>
            <h4 className="font-bold text-white text-sm truncate" title={item.identified_model}>
              {item.identified_model}
            </h4>
            <p className="text-[11px] text-slate-400 line-clamp-1 mt-0.5">{item.title}</p>
          </div>

          {/* Financial Breakdown */}
          <div className="space-y-1 my-1 bg-slate-900/80 p-2.5 rounded-lg border border-slate-800/80 text-xs">
            <div className="flex justify-between text-slate-400">
              <span>Asking Price:</span>
              <span className="font-mono text-slate-200 font-semibold">${item.asking_price.toFixed(2)}</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Est. Market Value:</span>
              <span className="font-mono text-slate-200 font-semibold">
                {item.market_value !== null ? `$${item.market_value.toFixed(2)}` : "N/A"}
              </span>
            </div>
            <div className="flex justify-between border-t border-slate-800 pt-1 mt-1">
              <span className="text-slate-300 font-medium">Profit Margin:</span>
              <span
                className={cn(
                  "font-mono font-bold",
                  isHighProfit ? "text-emerald-400" : item.profit_margin !== null ? "text-slate-200" : "text-slate-500"
                )}
              >
                {item.profit_margin !== null ? `${item.profit_margin.toFixed(1)}%` : "N/A"}
              </span>
            </div>
          </div>

          {/* Damage Notes Snippet */}
          {item.damage_notes && (
            <p className="text-[11px] text-slate-400 italic line-clamp-2 bg-slate-900/40 p-1.5 rounded border border-slate-800/40">
              "{item.damage_notes}"
            </p>
          )}

          {/* AI Confidence Progress Bar */}
          <div className="space-y-1">
            <div className="flex justify-between text-[11px] text-slate-400">
              <span>VLM Confidence</span>
              <span className="font-mono text-blue-300">{Math.round(item.confidence_score * 100)}%</span>
            </div>
            <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden">
              <div
                className="bg-blue-500 h-full rounded-full transition-all duration-300"
                style={{ width: `${Math.round(item.confidence_score * 100)}%` }}
              />
            </div>
          </div>

          {/* Quick Action Footer Hints */}
          <div className="flex items-center justify-between gap-2 pt-2 border-t border-slate-800/80 text-[10px]">
            <button
              onClick={(e) => {
                e.stopPropagation();
                onPurchase();
              }}
              className="text-emerald-400 hover:text-emerald-300 font-bold flex items-center gap-1 bg-emerald-950/60 hover:bg-emerald-900/80 px-2 py-1 rounded border border-emerald-800/60 transition-colors"
            >
              <ExternalLink className="w-3 h-3" />
              [W] Buy / Open
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onArchive();
              }}
              className="text-rose-400 hover:text-rose-300 font-bold flex items-center gap-1 bg-rose-950/60 hover:bg-rose-900/80 px-2 py-1 rounded border border-rose-800/60 transition-colors"
            >
              <Archive className="w-3 h-3" />
              [S] Archive
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Management Mode Data Table Sub-Component ---

interface ManagementTableProps {
  items: ArbitrageItem[];
  onUpdateItems: React.Dispatch<React.SetStateAction<ArbitrageItem[]>>;
}

function ManagementTable({ items, onUpdateItems }: ManagementTableProps) {
  const [sorting, setSorting] = useState<SortingState>([{ id: "profit_margin", desc: true }]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [globalFilter, setGlobalFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filteredData = useMemo(() => {
    if (statusFilter === "all") return items;
    return items.filter((item) => item.status === statusFilter);
  }, [items, statusFilter]);

  const handleBulkDelete = () => {
    const selectedIds = new Set(Object.keys(rowSelection));
    onUpdateItems((prev) => prev.filter((item) => !selectedIds.has(item.id)));
    setRowSelection({});
  };

  const handleBulkStatusChange = (newStatus: ItemStatus) => {
    const selectedIds = new Set(Object.keys(rowSelection));
    onUpdateItems((prev) =>
      prev.map((item) => (selectedIds.has(item.id) ? { ...item, status: newStatus } : item))
    );
    setRowSelection({});
  };

  const renderSortableHeader = (column: any, title: string) => {
    const isSorted = column.getIsSorted();
    return (
      <button
        onClick={column.getToggleSortingHandler()}
        className="flex items-center gap-1.5 font-semibold text-slate-300 hover:text-white transition-colors cursor-pointer select-none"
      >
        <span>{title}</span>
        {isSorted === "asc" ? (
          <ArrowUp className="w-3.5 h-3.5 text-blue-400" />
        ) : isSorted === "desc" ? (
          <ArrowDown className="w-3.5 h-3.5 text-blue-400" />
        ) : (
          <ArrowUpDown className="w-3.5 h-3.5 text-slate-500 opacity-60 hover:opacity-100" />
        )}
      </button>
    );
  };

  const columns = useMemo<ColumnDef<ArbitrageItem>[]>(
    () => [
      {
        id: "select",
        header: ({ table }) => (
          <input
            type="checkbox"
            checked={table.getIsAllPageRowsSelected()}
            onChange={table.getToggleAllPageRowsSelectedHandler()}
            aria-label="Select all"
            className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500 cursor-pointer"
          />
        ),
        cell: ({ row }) => (
          <input
            type="checkbox"
            checked={row.getIsSelected()}
            onChange={row.getToggleSelectedHandler()}
            aria-label={`Select ${row.original.identified_model}`}
            className="w-4 h-4 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500 cursor-pointer"
          />
        ),
        enableSorting: false,
      },
      {
        id: "image",
        header: "Preview",
        cell: ({ row }) => {
          const imgUrl = row.original.image_urls?.[0] || "/placeholder-camera.jpg";
          return (
            <div className="w-10 h-10 rounded-md overflow-hidden bg-slate-900 border border-slate-800 flex-shrink-0">
              <img
                src={imgUrl}
                alt={row.original.identified_model}
                className="w-full h-full object-cover"
              />
            </div>
          );
        },
        enableSorting: false,
      },
      {
        accessorKey: "identified_model",
        header: ({ column }) => renderSortableHeader(column, "Model Name"),
        cell: ({ row }) => (
          <div className="flex flex-col max-w-[220px]">
            <span className="font-semibold text-slate-100 text-sm truncate">
              {row.original.identified_model}
            </span>
            <span className="text-xs text-slate-400 truncate" title={row.original.title}>
              {row.original.title}
            </span>
          </div>
        ),
      },
      {
        accessorKey: "asking_price",
        header: ({ column }) => renderSortableHeader(column, "Asking Price"),
        cell: ({ row }) => (
          <span className="font-mono text-slate-100 font-semibold">
            ${row.original.asking_price.toFixed(2)}
          </span>
        ),
      },
      {
        accessorKey: "market_value",
        header: ({ column }) => renderSortableHeader(column, "Est. Market Value"),
        cell: ({ row }) => {
          const val = row.original.market_value;
          if (val === null || val === undefined) {
            return <span className="text-xs text-rose-400 italic">N/A (Major Damage)</span>;
          }
          return <span className="font-mono text-slate-300">${val.toFixed(2)}</span>;
        },
        sortingFn: (rowA, rowB) => {
          const a = rowA.original.market_value ?? -Infinity;
          const b = rowB.original.market_value ?? -Infinity;
          return a > b ? 1 : a < b ? -1 : 0;
        },
      },
      {
        accessorKey: "profit_margin",
        header: ({ column }) => renderSortableHeader(column, "Profit Margin"),
        cell: ({ row }) => {
          const margin = row.original.profit_margin;
          if (margin === null || margin === undefined) {
            return <span className="text-xs text-rose-400 italic">N/A (Major Damage)</span>;
          }
          const isHigh = margin >= 40;
          return (
            <span
              className={cn(
                "inline-flex items-center px-2 py-0.5 rounded text-xs font-mono border font-semibold",
                isHigh
                  ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                  : "bg-slate-800 text-slate-300 border-slate-700"
              )}
            >
              {margin >= 0 ? `+${margin.toFixed(1)}%` : `${margin.toFixed(1)}%`}
            </span>
          );
        },
        sortingFn: (rowA, rowB) => {
          const a = rowA.original.profit_margin ?? -Infinity;
          const b = rowB.original.profit_margin ?? -Infinity;
          return a > b ? 1 : a < b ? -1 : 0;
        },
      },
      {
        accessorKey: "status",
        header: ({ column }) => renderSortableHeader(column, "Status"),
        cell: ({ row }) => {
          const status = row.original.status;
          const statusMap: Record<ItemStatus, { label: string; style: string }> = {
            active: { label: "Active", style: "bg-emerald-950/80 text-emerald-400 border-emerald-800" },
            purchased: { label: "Purchased", style: "bg-sky-950/80 text-sky-400 border-sky-800" },
            in_transit: { label: "In Transit", style: "bg-indigo-950/80 text-indigo-400 border-indigo-800" },
            relisted: { label: "Relisted", style: "bg-purple-950/80 text-purple-400 border-purple-800" },
            archived: { label: "Archived", style: "bg-slate-800 text-slate-400 border-slate-700" },
          };
          const config = statusMap[status] || statusMap.active;
          return (
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${config.style}`}>
              {config.label}
            </span>
          );
        },
      },
      {
        accessorKey: "source_badge",
        header: ({ column }) => renderSortableHeader(column, "Pipeline Source"),
        cell: ({ row }) => (
          <Badge variant={row.original.source_badge === "Exact Match" ? "cyan" : "secondary"} className="text-[10px]">
            {row.original.source_badge}
          </Badge>
        ),
      },
      {
        accessorKey: "damage_severity",
        header: ({ column }) => renderSortableHeader(column, "Damage"),
        cell: ({ row }) => {
          const damage = row.original.damage_severity;
          if (damage === "major") {
            return (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-800">
                <AlertTriangle className="w-3 h-3 text-rose-400" />
                Major
              </span>
            );
          }
          if (damage === "minor") {
            return (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-950 text-amber-300 border border-amber-800">
                Minor
              </span>
            );
          }
          return <span className="text-xs text-slate-500">None</span>;
        },
      },
      {
        id: "actions",
        header: "Actions",
        cell: ({ row }) => (
          <a
            href={row.original.listing_url}
            target="_blank"
            rel="noopener noreferrer"
            className="p-1.5 text-slate-400 hover:text-emerald-400 transition-colors inline-block"
            title="Open eBay Listing"
          >
            <ExternalLink className="w-4 h-4" />
          </a>
        ),
      },
    ],
    []
  );

  const table = useReactTable({
    data: filteredData,
    columns,
    state: {
      sorting,
      rowSelection,
      globalFilter,
    },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableRowSelection: true,
    getRowId: (row) => row.id,
  });

  const selectedCount = Object.keys(rowSelection).length;

  return (
    <div className="w-full space-y-4">
      {/* Table Controls Header Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 bg-slate-900/60 p-4 rounded-xl border border-slate-800">
        <div className="flex items-center gap-3">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search model, title..."
              value={globalFilter ?? ""}
              onChange={(e) => setGlobalFilter(e.target.value)}
              className="pl-9 pr-4 py-1.5 text-xs bg-slate-950 border border-slate-700 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>

          <div className="flex items-center gap-1.5">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="py-1.5 px-3 text-xs bg-slate-950 border border-slate-700 rounded-lg text-slate-200 focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Statuses ({items.length})</option>
              <option value="active">Active</option>
              <option value="purchased">Purchased</option>
              <option value="in_transit">In Transit</option>
              <option value="relisted">Relisted</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>

        <div className="text-xs text-slate-400 font-mono">
          Showing {table.getRowModel().rows.length} of {items.length} records
        </div>
      </div>

      {/* Data Table Wrapper */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-950 shadow-xl">
        <table className="w-full text-left text-xs border-collapse">
          <thead className="bg-slate-900/90 border-b border-slate-800 text-slate-300 sticky top-0 z-10">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => (
                  <th key={header.id} className="py-3 px-4 font-semibold select-none">
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="text-center py-12 text-slate-500 text-sm">
                  No items found matching criteria.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className={cn(
                    "hover:bg-slate-800/50 transition-colors",
                    row.getIsSelected() && "bg-blue-950/30"
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="py-3 px-4 align-middle">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Floating Action Bar for Bulk Operations */}
      {selectedCount > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 bg-slate-900/95 backdrop-blur-md border border-slate-700 text-white shadow-2xl rounded-full px-6 py-3 flex items-center gap-4 animate-in fade-in slide-in-from-bottom-5 duration-200">
          <span className="text-xs font-semibold px-2.5 py-1 bg-blue-500/20 text-blue-300 border border-blue-500/30 rounded-full">
            {selectedCount} selected
          </span>

          <div className="h-4 w-[1px] bg-slate-700" />

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleBulkStatusChange("purchased")}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-emerald-600/30 hover:text-emerald-300 border border-slate-700 rounded-md transition-all text-slate-200"
              title="Mark Selected as Purchased"
            >
              <ShoppingBag className="w-3.5 h-3.5 text-emerald-400" />
              <span>Purchased</span>
            </button>

            <button
              onClick={() => handleBulkStatusChange("in_transit")}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-sky-600/30 hover:text-sky-300 border border-slate-700 rounded-md transition-all text-slate-200"
              title="Mark Selected as In Transit"
            >
              <Truck className="w-3.5 h-3.5 text-sky-400" />
              <span>In Transit</span>
            </button>

            <button
              onClick={() => handleBulkStatusChange("relisted")}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-purple-600/30 hover:text-purple-300 border border-slate-700 rounded-md transition-all text-slate-200"
              title="Mark Selected as Relisted"
            >
              <RotateCcw className="w-3.5 h-3.5 text-purple-400" />
              <span>Relisted</span>
            </button>

            <button
              onClick={() => handleBulkStatusChange("archived")}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-amber-600/30 hover:text-amber-300 border border-slate-700 rounded-md transition-all text-slate-200"
              title="Archive Selected"
            >
              <Archive className="w-3.5 h-3.5 text-amber-400" />
              <span>Archive</span>
            </button>
          </div>

          <div className="h-4 w-[1px] bg-slate-700" />

          <button
            onClick={handleBulkDelete}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-rose-950/80 text-rose-300 hover:bg-rose-600 hover:text-white border border-rose-800 rounded-md transition-all"
            title="Delete Selected Items"
          >
            <Trash2 className="w-3.5 h-3.5" />
            <span>Delete</span>
          </button>

          <button
            onClick={() => setRowSelection({})}
            className="text-xs text-slate-400 hover:text-slate-200 ml-1 underline underline-offset-2"
          >
            Deselect
          </button>
        </div>
      )}
    </div>
  );
}

// --- Main Arbitrage Command Center Component ---

export default function ArbitrageCommandCenter() {
  const [viewMode, setViewMode] = useState<"triage" | "management">("triage");
  const [items, setItems] = useState<ArbitrageItem[]>(INITIAL_DATASET);
  const [activeCardIndex, setActiveCardIndex] = useState<number>(0);

  // Active items for Triage Mode (filtering out archived items and major damage items)
  const triageItems = useMemo(
    () => items.filter((item) => item.status === "active" && item.damage_severity !== "major"),
    [items]
  );

  // Background Link & Image Pre-fetching
  usePrefetchTriageQueue(triageItems, activeCardIndex);

  // Handler for Purchasing an Item ('W' key or click)
  const handlePurchaseItem = (item: ArbitrageItem) => {
    if (typeof window !== "undefined" && item.listing_url) {
      window.open(item.listing_url, "_blank", "noopener,noreferrer");
    }
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, status: "purchased" } : i))
    );
  };

  // Handler for Archiving an Item ('S' key or right click)
  const handleArchiveItem = (item: ArbitrageItem) => {
    setItems((prev) =>
      prev.map((i) => (i.id === item.id ? { ...i, status: "archived" } : i))
    );
  };

  // Global Keyboard Shortcuts Listener ('W' to buy, 'S' to archive, Arrow keys to navigate)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Ignore keypresses if focus is inside form input elements
      const activeEl = document.activeElement;
      if (
        activeEl &&
        (activeEl.tagName === "INPUT" ||
          activeEl.tagName === "TEXTAREA" ||
          activeEl.tagName === "SELECT")
      ) {
        return;
      }

      if (viewMode !== "triage" || triageItems.length === 0) return;

      const currentItem = triageItems[activeCardIndex] || triageItems[0];
      if (!currentItem) return;

      const key = e.key.toLowerCase();
      if (key === "w") {
        e.preventDefault();
        handlePurchaseItem(currentItem);
      } else if (key === "s") {
        e.preventDefault();
        handleArchiveItem(currentItem);
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setActiveCardIndex((prev) => (prev + 1) % triageItems.length);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setActiveCardIndex((prev) => (prev - 1 + triageItems.length) % triageItems.length);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [viewMode, triageItems, activeCardIndex]);

  // Adjust active card index if items are removed
  useEffect(() => {
    if (activeCardIndex >= triageItems.length && triageItems.length > 0) {
      setActiveCardIndex(triageItems.length - 1);
    }
  }, [triageItems.length, activeCardIndex]);

  const activeTriageCount = triageItems.length;
  const highMarginCount = items.filter(
    (i) => i.profit_margin !== null && i.profit_margin >= 40
  ).length;

  return (
    <div className="flex min-h-screen flex-col bg-slate-950 text-slate-100 font-sans antialiased">
      {/* Top Header Navigation */}
      <header className="sticky top-0 z-40 flex h-16 items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6 backdrop-blur-md">
        <div className="flex items-center space-x-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-600/20 border border-blue-500/30 text-blue-400 shadow-sm">
            <Zap className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center gap-2">
              Y2K Arbitrage Command Center
              <Badge variant="cyan" className="text-[10px] px-1.5 py-0 font-mono">
                v1.0
              </Badge>
            </h1>
            <p className="text-xs text-slate-400">Real-Time Deal Triage & Inventory Intelligence</p>
          </div>
        </div>

        {/* Center Dual Mode Switcher */}
        <div className="flex items-center rounded-lg border border-slate-800 bg-slate-900/90 p-1">
          <button
            onClick={() => setViewMode("triage")}
            className={cn(
              "flex items-center space-x-2 rounded-md px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer",
              viewMode === "triage"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            )}
          >
            <LayoutGrid className="h-3.5 w-3.5" />
            <span>Triage Grid ({activeTriageCount})</span>
          </button>
          <button
            onClick={() => setViewMode("management")}
            className={cn(
              "flex items-center space-x-2 rounded-md px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer",
              viewMode === "management"
                ? "bg-blue-600 text-white shadow-sm"
                : "text-slate-400 hover:text-slate-200"
            )}
          >
            <TableIcon className="h-3.5 w-3.5" />
            <span>Management Mode ({items.length})</span>
          </button>
        </div>

        {/* Right Header Metrics */}
        <div className="flex items-center space-x-3">
          <Badge variant="success" className="gap-1 text-xs py-1">
            <ShieldCheck className="h-3.5 w-3.5" />
            {highMarginCount} High Profit (&gt;40%)
          </Badge>
          <Button variant="outline" size="sm" className="gap-1.5 border-slate-800 text-xs">
            <RefreshCw className="h-3.5 w-3.5" />
            Live Sync
          </Button>
        </div>
      </header>

      {/* Main Mode View */}
      <main className="flex-1 p-6">
        {viewMode === "triage" ? (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                Active Triage Queue ({activeTriageCount} Remaining)
              </h2>
              <div className="text-xs text-slate-400 flex items-center gap-2">
                <span>Shortcuts:</span>
                <kbd className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-emerald-400 font-mono text-[11px] font-bold">
                  [W] Buy / Open
                </kbd>
                <kbd className="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-rose-400 font-mono text-[11px] font-bold">
                  [S] Archive / Skip
                </kbd>
                <span className="text-slate-500">| Mouse Wheel: Cycle Images</span>
              </div>
            </div>

            {triageItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-20 border border-dashed border-slate-800 rounded-xl bg-slate-900/30 text-center">
                <CheckCircle2 className="w-12 h-12 text-emerald-400 mb-3" />
                <h3 className="text-lg font-bold text-slate-200">All Deals Triaged!</h3>
                <p className="text-xs text-slate-400 max-w-md mt-1 mb-4">
                  There are no active camera listings remaining in the fast review queue.
                </p>
                <Button variant="outline" onClick={() => setViewMode("management")}>
                  Switch to Management Mode
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                {triageItems.map((item, idx) => (
                  <TriageCard
                    key={item.id}
                    item={item}
                    isActive={idx === activeCardIndex}
                    onSelect={() => setActiveCardIndex(idx)}
                    onPurchase={() => handlePurchaseItem(item)}
                    onArchive={() => handleArchiveItem(item)}
                  />
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
                Inventory & Pipeline Management Table
              </h2>
              <p className="text-xs text-slate-500">
                Complete inventory database including hidden, archived, and major damage items.
              </p>
            </div>
            <ManagementTable items={items} onUpdateItems={setItems} />
          </div>
        )}
      </main>
    </div>
  );
}
