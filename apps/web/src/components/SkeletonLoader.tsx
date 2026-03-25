interface SkeletonLoaderProps {
  count?: number;
  className?: string;
}

export default function SkeletonLoader({ count = 3, className = '' }: SkeletonLoaderProps) {
  return (
    <div className={`space-y-3 ${className}`} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="animate-pulse rounded-lg bg-gray-100 p-4">
          <div className="h-4 bg-gray-200 rounded w-1/3 mb-2" />
          <div className="h-3 bg-gray-200 rounded w-2/3" />
        </div>
      ))}
    </div>
  );
}
