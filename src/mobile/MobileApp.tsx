import { Routes, Route, Navigate } from 'react-router-dom'
import { MobileShell } from './MobileShell'

import { DingshuluList } from './tabs/DingshuluTab/DingshuluList'
import { DingshuluDetail } from './tabs/DingshuluTab/DingshuluDetail'
import { TrackingList } from './tabs/TrackingTab/TrackingList'
import { TrackingDetail } from './tabs/TrackingTab/TrackingDetail'
import { TianjiList } from './tabs/TianjiTab/TianjiList'
import { TianjiDetail } from './tabs/TianjiTab/TianjiDetail'
import { SubmitForm } from './tabs/SubmitTab/SubmitForm'
import { AvatarChat } from './tabs/AvatarTab/AvatarChat'

export function MobileApp() {
  return (
    <MobileShell>
      <Routes>
        <Route index element={<Navigate to="dingshulu" replace />} />
        <Route path="dingshulu" element={<DingshuluList />} />
        <Route path="dingshulu/:id" element={<DingshuluDetail />} />
        <Route path="tracking" element={<TrackingList />} />
        <Route path="tracking/:code" element={<TrackingDetail />} />
        <Route path="tianyan" element={<TianjiList />} />
        <Route path="tianyan/:id" element={<TianjiDetail />} />
        <Route path="submit" element={<SubmitForm />} />
        <Route path="avatar" element={<AvatarChat />} />
      </Routes>
    </MobileShell>
  )
}
