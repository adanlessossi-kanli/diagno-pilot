interface DiagnoPilotLogoProps {
  size?: number;
  className?: string;
}

export default function DiagnoPilotLogo({ size = 32, className }: DiagnoPilotLogoProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      role="img"
      aria-label="Diagno-Pilot logo"
      data-logo="diagno-pilot"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Warm-tone accent circle (African identity) */}
      <circle cx="16" cy="16" r="14" fill="#F59E0B" opacity="0.25" />
      <circle cx="16" cy="16" r="11" fill="#F59E0B" opacity="0.15" />

      {/* Stylized medical cross in primary blue */}
      <rect x="13" y="6" width="6" height="20" rx="2" fill="#2563EB" />
      <rect x="6" y="13" width="20" height="6" rx="2" fill="#2563EB" />
    </svg>
  );
}
