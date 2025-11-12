/**
 * AppHeader - Global application header
 * Features: Entity selection, global settings, theme toggle
 */

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EntitySelector } from "./entity-selector";
import { ModeToggle } from "@/components/mode-toggle";
import { Settings, Zap } from "lucide-react";
import type { AgentInfo, WorkflowInfo } from "@/types";
import { useDevUIStore } from "@/stores";

interface AppHeaderProps {
  agents: AgentInfo[];
  workflows: WorkflowInfo[];
  entities?: (AgentInfo | WorkflowInfo)[];
  selectedItem?: AgentInfo | WorkflowInfo;
  onSelect: (item: AgentInfo | WorkflowInfo) => void;
  onBrowseGallery?: () => void;
  isLoading?: boolean;
  onSettingsClick?: () => void;
}

export function AppHeader({
  agents,
  workflows,
  entities,
  selectedItem,
  onSelect,
  onBrowseGallery,
  isLoading = false,
  onSettingsClick,
}: AppHeaderProps) {
  const { oaiMode } = useDevUIStore();

  return (
    <header className="flex h-14 items-center gap-4 border-b px-4">
      <div className="flex items-center gap-2 font-semibold">
        <svg
          width="24"
          height="24"
          viewBox="0 0 805 805"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="flex-shrink-0"
        >
          <path
            d="M402.488 119.713C439.197 119.713 468.955 149.472 468.955 186.18C468.955 192.086 471.708 197.849 476.915 200.635L546.702 237.977C555.862 242.879 566.95 240.96 576.092 236.023C585.476 230.955 596.218 228.078 607.632 228.078C644.341 228.078 674.098 257.836 674.099 294.545C674.099 316.95 663.013 336.765 646.028 348.806C637.861 354.595 631.412 363.24 631.412 373.251V430.818C631.412 440.83 637.861 449.475 646.028 455.264C663.013 467.305 674.099 487.121 674.099 509.526C674.099 546.235 644.341 575.994 607.632 575.994C598.598 575.994 589.985 574.191 582.133 570.926C573.644 567.397 563.91 566.393 555.804 570.731L469.581 616.867C469.193 617.074 468.955 617.479 468.955 617.919C468.955 654.628 439.197 684.386 402.488 684.386C365.779 684.386 336.021 654.628 336.021 617.919C336.021 616.802 335.423 615.765 334.439 615.238L249.895 570C241.61 565.567 231.646 566.713 223.034 570.472C214.898 574.024 205.914 575.994 196.47 575.994C159.761 575.994 130.002 546.235 130.002 509.526C130.002 486.66 141.549 466.49 159.13 454.531C167.604 448.766 174.349 439.975 174.349 429.726V372.538C174.349 362.289 167.604 353.498 159.13 347.734C141.549 335.774 130.002 315.604 130.002 292.738C130.002 256.029 159.761 226.271 196.47 226.271C208.223 226.271 219.263 229.322 228.843 234.674C238.065 239.827 249.351 241.894 258.666 236.91L328.655 199.459C333.448 196.895 336.021 191.616 336.021 186.18C336.021 149.471 365.779 119.713 402.488 119.713ZM475.716 394.444C471.337 396.787 468.955 401.586 468.955 406.552C468.955 429.68 457.142 450.048 439.221 461.954C430.571 467.7 423.653 476.574 423.653 486.959V537.511C423.653 547.896 430.746 556.851 439.379 562.622C449 569.053 461.434 572.052 471.637 566.592L527.264 536.826C536.887 531.677 541.164 520.44 541.164 509.526C541.164 485.968 553.42 465.272 571.904 453.468C580.846 447.757 588.054 438.749 588.054 428.139V371.427C588.054 363.494 582.671 356.676 575.716 352.862C569.342 349.366 561.663 348.454 555.253 351.884L475.716 394.444ZM247.992 349.841C241.997 346.633 234.806 347.465 228.873 350.785C222.524 354.337 217.706 360.639 217.706 367.915V429.162C217.706 439.537 224.611 448.404 233.248 454.152C251.144 466.062 262.937 486.417 262.937 509.526C262.937 519.654 267.026 529.991 275.955 534.769L334.852 566.284C344.582 571.49 356.362 568.81 365.528 562.667C373.735 557.166 380.296 548.643 380.296 538.764V486.305C380.296 476.067 373.564 467.282 365.103 461.516C347.548 449.552 336.021 429.398 336.021 406.552C336.021 400.967 333.389 395.536 328.465 392.902L247.992 349.841ZM270.019 280.008C265.421 282.469 262.936 287.522 262.937 292.738C262.937 293.308 262.929 293.876 262.915 294.443C262.615 306.354 266.961 318.871 277.466 324.492L334.017 354.751C344.13 360.163 356.442 357.269 366.027 350.969C376.495 344.088 389.024 340.085 402.488 340.085C416.203 340.085 428.947 344.239 439.532 351.357C449.163 357.834 461.63 360.861 471.864 355.385L526.625 326.083C537.106 320.474 541.458 307.999 541.182 296.115C541.17 295.593 541.164 295.069 541.164 294.545C541.164 288.551 538.376 282.696 533.091 279.868L463.562 242.664C454.384 237.753 443.274 239.688 434.123 244.65C424.716 249.75 413.941 252.647 402.488 252.647C390.83 252.647 379.873 249.646 370.348 244.373C361.148 239.281 349.917 237.256 340.646 242.217L270.019 280.008Z"
            fill="url(#paint0_linear_510_1294)"
          />
          <defs>
            <linearGradient
              id="paint0_linear_510_1294"
              x1="255.628"
              y1="-34.3245"
              x2="618.483"
              y2="632.032"
              gradientUnits="userSpaceOnUse"
            >
              <stop stopColor="#D59FFF" />
              <stop offset="1" stopColor="#8562C5" />
            </linearGradient>
          </defs>
        </svg>
        Dev UI
        {/* Mode Badge */}
        {oaiMode.enabled && (
          <Badge variant="secondary" className="gap-1 ml-2">
            <Zap className="h-3 w-3" />
            OpenAI: {oaiMode.model}
          </Badge>
        )}
      </div>

      {/* Show entity selector only when NOT in OAI mode */}
      {!oaiMode.enabled && (
        <EntitySelector
          agents={agents}
          workflows={workflows}
          entities={entities}
          selectedItem={selectedItem}
          onSelect={onSelect}
          onBrowseGallery={onBrowseGallery}
          isLoading={isLoading}
        />
      )}

      <div className="flex-1"></div>

      <div className="flex items-center gap-2 ml-auto">
        <ModeToggle />
        <Button variant="ghost" size="sm" onClick={(e: React.MouseEvent) => { e.stopPropagation(); onSettingsClick?.(); }}>
          <Settings className="h-4 w-4" />
        </Button>
      </div>
    </header>
  );
}
