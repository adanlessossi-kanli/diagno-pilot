import Image from 'next/image';

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
  image?: { src: string; alt: string };
}

export default function EmptyState({ title, description, action, image }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      {image ? (
        <div className="relative w-40 h-40 mb-4 rounded-lg overflow-hidden bg-gray-100">
          <Image
            src={image.src}
            alt={image.alt}
            fill
            className="object-cover"
            sizes="160px"
          />
        </div>
      ) : (
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="h-16 w-16 text-primary-100 mb-4"
          fill="none"
          viewBox="0 0 64 64"
          aria-hidden="true"
        >
          <circle cx="32" cy="32" r="30" stroke="currentColor" strokeWidth="2" />
          <path
            d="M32 20v14M32 40v2"
            stroke="#2563EB"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </svg>
      )}
      <h2 className="text-lg font-semibold text-gray-800 mb-1">{title}</h2>
      {description && (
        <p className="text-sm text-gray-500 max-w-xs mb-4">{description}</p>
      )}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-2 px-5 py-2 bg-primary-600 text-white text-sm font-medium rounded hover:bg-primary-700 transition-colors"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
