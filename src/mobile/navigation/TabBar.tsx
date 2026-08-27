import { NavLink } from 'react-router-dom'
import { TABS } from './TabConfig'

export function TabBar() {
  return (
    <nav className="flex-shrink-0 h-14 flex justify-around items-stretch border-t border-[#2A2A2A] bg-[#050401]/95 backdrop-blur-sm safe-bottom">
      {TABS.map((tab) => {
        const Icon = tab.icon
        return (
          <NavLink
            key={tab.id}
            to={tab.route}
            className="flex flex-col items-center justify-center flex-1 gap-0.5 transition-colors min-w-0 px-0.5"
            style={({ isActive }) => ({
              color: isActive ? '#ADFF00' : '#555',
            })}
          >
            <Icon size={18} className="flex-shrink-0" />
            <span className="text-[11px] leading-tight whitespace-nowrap">
              {tab.label}
            </span>
          </NavLink>
        )
      })}
    </nav>
  )
}
