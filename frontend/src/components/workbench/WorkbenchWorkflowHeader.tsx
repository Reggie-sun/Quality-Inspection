import { zhCN } from "../../copy/zhCN";


type WorkbenchWorkflowHeaderProps = {
  activeStage: number;
  onReset?: () => void;
};


export function WorkbenchWorkflowHeader({
  activeStage,
  onReset,
}: WorkbenchWorkflowHeaderProps) {
  return (
    <header className="workflow-header" aria-label="工程图纸检验流程">
      <div
        className="workflow-header__brand"
        aria-label={`${zhCN.brand} ${zhCN.product}`}
      >
        <strong>{zhCN.brand}</strong>
        <span>{zhCN.product}</span>
      </div>

      <nav className="workflow-steps" aria-label={zhCN.workbench.stageNavigation}>
        <ol>
          {zhCN.stages.map((stage, index) => {
            const state = index < activeStage
              ? "complete"
              : index === activeStage ? "current" : "pending";
            const stateLabel = state === "complete"
              ? "已完成"
              : state === "current" ? "当前阶段" : "待开始";
            return (
              <li
                key={stage}
                data-state={state}
                aria-current={state === "current" ? "step" : undefined}
                aria-label={`${stage}，${stateLabel}`}
              >
                <span className="workflow-step__node" aria-hidden="true">
                  {index + 1}
                </span>
                <span className="workflow-step__copy">
                  <strong>{stage}</strong>
                  <small>{zhCN.stageDescriptions[index]}</small>
                </span>
              </li>
            );
          })}
        </ol>
      </nav>

      <button
        type="button"
        className="workflow-header__action"
        onClick={onReset}
      >
        {zhCN.upload.another}
      </button>
    </header>
  );
}
