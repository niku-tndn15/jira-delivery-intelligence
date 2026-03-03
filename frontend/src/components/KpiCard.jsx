const ACCENT = {
  azure:  { bg: 'bg-azure/10',  border: 'border-azure/20',  text: 'text-azure'  },
  teal:   { bg: 'bg-teal/10',   border: 'border-teal/20',   text: 'text-teal'   },
  violet: { bg: 'bg-violet/10', border: 'border-violet/20', text: 'text-violet' },
  amber:  { bg: 'bg-amber/10',  border: 'border-amber/20',  text: 'text-amber'  },
  rose:   { bg: 'bg-rose/10',   border: 'border-rose/20',   text: 'text-rose'   },
  sage:   { bg: 'bg-sage/10',   border: 'border-sage/20',   text: 'text-sage'   },
}

export default function KpiCard({
  icon, color = 'azure', label, value, sub, quality, loading, delay = '0ms',
}) {
  const accent = ACCENT[color] ?? ACCENT.azure

  return (
    <div
      className="panel p-5 flex flex-col gap-3 animate-fade-up"
      style={{ animationDelay: delay }}
    >
      {/* Icon + label */}
      <div className="flex items-center justify-between">
        <span className="label">{label}</span>
        <div className={`w-7 h-7 rounded-lg flex items-center justify-center ${accent.bg} border ${accent.border}`}>
          <span className={accent.text}>{icon}</span>
        </div>
      </div>

      {/* Big number */}
      {loading ? (
        <div className="space-y-2">
          <div className="skeleton h-8 w-28" />
          <div className="skeleton h-3 w-40" />
        </div>
      ) : (
        <>
          <span className={`font-display text-3xl leading-none tracking-tight ${quality ?? 'text-snow'}`}>
            {value}
          </span>
          {sub && (
            <span className="label text-ghost leading-relaxed">{sub}</span>
          )}
        </>
      )}
    </div>
  )
}
