import { Suspense } from "react";
import ActivityCard from "@/components/ActivityCard";
import AirCard from "@/components/AirCard";
import { CardSkeleton } from "@/components/Card";
import ChatPanel from "@/components/ChatPanel"; // ← 추가
import HourlyCard from "@/components/HourlyCard";
import UvCard from "@/components/UvCard";
import WeatherCard from "@/components/WeatherCard";

export const dynamic = "force-dynamic"; // 요청마다 새로 렌더링

// 지금은 분당구 고정. 지역 선택은 다음 단계에서 붙인다.
const LOCATION = "분당구";
const ACTIVITY = "러닝";

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl p-6">
      <h1 className="mb-1 text-2xl font-bold">오늘의 날씨 브리핑</h1>
      <p className="mb-6 text-sm text-zinc-500">📍 {LOCATION}</p>

      {/* 카드마다 Suspense를 따로 걸어서, 느리거나 실패한 카드가 나머지를 막지 않는다 */}
      <div className="grid gap-4 md:grid-cols-2">
        <Suspense fallback={<CardSkeleton title="현재 날씨" />}>
          <WeatherCard location={LOCATION} />
        </Suspense>
        <Suspense fallback={<CardSkeleton title="활동 추천" />}>
          <ActivityCard location={LOCATION} activity={ACTIVITY} />
        </Suspense>
        <Suspense fallback={<CardSkeleton title="시간대별 예보" />}>
          <HourlyCard location={LOCATION} />
        </Suspense>
        <Suspense fallback={<CardSkeleton title="대기질" />}>
          <AirCard location={LOCATION} />
        </Suspense>
        <Suspense fallback={<CardSkeleton title="자외선" />}>
          <UvCard location={LOCATION} />
        </Suspense>
      </div>

      {/* 웹 채팅: 클라이언트 컴포넌트. 카드와 분리해 아래에 둔다 */}
      <div className="mt-6">
        <ChatPanel />
      </div>
    </main>
  );
}