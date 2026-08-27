import { Drawer } from 'vaul'

export function MobileSheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <Drawer.Root open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm" />
        <Drawer.Content className="fixed bottom-0 left-0 right-0 z-50 bg-[#0A0A0A] border-t border-[#2A2A2A] rounded-t-lg max-h-[80vh] flex flex-col">
          <div className="mx-auto mt-3 mb-2 w-10 h-1 bg-[#2A2A2A] rounded-full flex-shrink-0" />
          <Drawer.Title className="text-center text-sm font-mono text-[#F2F4F3] tracking-wider mb-1">
            {title}
          </Drawer.Title>
          <div className="overflow-y-auto flex-1 px-4 pb-6">
            {children}
          </div>
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  )
}
