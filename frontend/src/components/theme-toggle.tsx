import { MoonIcon, SunIcon } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useTheme } from '@/lib/theme';

export function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  const label = theme === 'dark' ? 'Cambiar a modo día' : 'Cambiar a modo noche';
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      onClick={toggle}
      aria-label={label}
      title={label}
      className={className}
    >
      {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
    </Button>
  );
}
