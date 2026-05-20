export {
  Dialog as Sheet,
  DialogPortal as SheetPortal,
  DialogOverlay as SheetOverlay,
  DialogTrigger as SheetTrigger,
  DialogClose as SheetClose,
  DialogHeader as SheetHeader,
  DialogTitle as SheetTitle,
  DialogDescription as SheetDescription,
} from "@/components/ui/dialog";
import { DialogContent } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

function SheetContent({ className, ...props }: React.ComponentProps<typeof DialogContent>) {
  return <DialogContent className={cn("left-auto right-0 top-0 h-full w-80 max-w-[85vw] translate-x-0 translate-y-0 rounded-none", className)} {...props} />;
}

export { SheetContent };
