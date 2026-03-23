"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const items = [
  { href: "/", label: "首页" },
  { href: "/discover", label: "探索导师" },
  { href: "/advisor-ai", label: "AI 推荐" },
  { href: "/mentors", label: "导师库" },
  { href: "/my-mentors", label: "我的导师库" },
  { href: "/timeline", label: "Timeline" },
  { href: "/settings", label: "设置" },
];

export default function MainNav() {
  const pathname = usePathname();

  return (
    <div className="nav-row">
      {items.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        return (
          <Link key={item.href} href={item.href} className={`nav-pill${active ? " active" : ""}`}>
            {item.label}
          </Link>
        );
      })}
    </div>
  );
}
