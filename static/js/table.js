// 检查表格宽度（测试用）
function getwidth() {
  const a = document.getElementById("logs");
  console.log(a.offsetWidth);
  console.log(a.scrollWidth);
  console.log(a.clientWidth);
  const b = document.getElementById("page");
  console.log(b.offsetWidth);
  console.log(b.scrollWidth);
  console.log(b.clientWidth);
  const c = document.getElementById("icon-title");
  console.log(c.offsetWidth);
  console.log(c.scrollWidth);
  console.log(c.clientWidth);
}

// 初始化表格内容
class InitializeTable {
  constructor() {

    // 表头排序
    this.values = [
      "id",
      "target",
      "mode",
      "reason",
      "group_id",
      "duration",
      "operator",
      "time",
      "image",
    ];
    this.count_risk = null
    this.InitializeEditForm = new InitializeEditForm(this.values, this)
  }

  // 替换时间单位
  formatDuration(duration) {
    if (!duration) return "不适用";

    // 解析格式：1m、5h、2d、3w、1M
    const unitMap = {
      s: "秒",
      m: "分钟",
      h: "小时",
      d: "天",
      w: "周",
      M: "月",
    };

    const match = duration.match(/^(\d+)([smhdwM])$/);
    if (match) {
      const value = parseInt(match[1]);
      const unit = unitMap[match[2]];
      return `${value}${unit}`;
    }

    // 自动转换为最合适的单位
    const seconds = parseInt(duration);
    return this.autoFormatSeconds(seconds);
  }

  // 自动换算时间
  autoFormatSeconds(totalSeconds) {
    const units = [
      { value: 2592000, unit: "月", single: "M" }, // 30天
      { value: 604800, unit: "周", single: "w" }, // 7天
      { value: 86400, unit: "天", single: "d" }, // 1天
      { value: 3600, unit: "小时", single: "h" }, // 1小时
      { value: 60, unit: "分钟", single: "m" }, // 1分钟
      { value: 1, unit: "秒", single: "s" },
    ];

    // 找出最适合的单位
    for (const unit of units) {
      if (totalSeconds >= unit.value) {
        const value = Math.round((totalSeconds / unit.value) * 10) / 10; // 保留1位小数
        // 如果值很小但单位很大（如0.1月），尝试更小的单位
        if (value < 1 && unit.value > 1) continue;

        // 如果是整数，显示整数，否则显示1位小数
        const displayValue = Number.isInteger(value) ? value : value.toFixed(1);
        return `${displayValue}${unit.unit}`;
      }
    }

    // 小于1秒的情况
    return `${totalSeconds}秒`;
  }

  // 头像预加载函数
  preloadAvatar(cell, avatarUrl) {
    const img = new Image();

    img.onload = function () {
      // 图片存在，设置头像
      cell.classList.add("has-avatar", "avatar-loaded");
      cell.style.setProperty("--avatar-image", `url(${avatarUrl})`);
    };

    img.onerror = function () {
      // 图片不存在，使用默认头像
      cell.classList.add("no-avatar");
    };

    // 添加超时处理
    const timeoutId = setTimeout(() => {
      img.onload = img.onerror = null;
      cell.classList.add("no-avatar");
    }, 3000);

    img.onload = img.onerror = function () {
      clearTimeout(timeoutId);
      if (this.complete && this.naturalHeight !== 0) {
        cell.classList.add("has-avatar", "avatar-loaded");
        cell.style.setProperty("--avatar-image", `url(${avatarUrl})`);
      } else {
        cell.classList.add("no-avatar");
      }
    };

    img.src = avatarUrl;
  }

  // 添加点击复制效果
  addCopyToClipboard(element, options = {}) {
    // 默认配置
    const config = {
      text: element.textContent || "",
      successMsg: "已复制到剪贴板",
      errorMsg: "复制失败，请手动复制",
      hoverCursor: "pointer",
      ...options,
    };

    // 1. 设置鼠标样式为可点击
    element.style.cursor = config.hoverCursor;

    // 2. 添加点击事件监听
    element.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();

      try {
        // 获取要复制的文本
        const textToCopy =
          typeof config.text === "function" ? config.text() : config.text;

        // 使用现代 Clipboard API
        await navigator.clipboard.writeText(textToCopy);

        // 显示成功提示
        this.showCopyFeedback(element, config.successMsg, "success");
      } catch (error) {
        console.error("复制失败:", error);

        // 降级方案：使用 document.execCommand
        try {
          const textarea = document.createElement("textarea");
          const textToCopy =
            typeof config.text === "function" ? config.text() : config.text;

          textarea.value = textToCopy;
          textarea.style.position = "fixed";
          textarea.style.opacity = "0";
          document.body.appendChild(textarea);
          textarea.select();
          textarea.setSelectionRange(0, 99999); // 移动端支持

          const success = document.execCommand("copy");
          document.body.removeChild(textarea);

          if (success) {
            this.showCopyFeedback(element, config.successMsg, "success");
          } else {
            throw new Error("execCommand 复制失败");
          }
        } catch (fallbackError) {
          this.showCopyFeedback(element, config.errorMsg, "error");
        }
      }
    });
  }

  // 添加复制通知
  showCopyFeedback(element, message, type = "success") {
    // 移除已有的提示
    const existingTooltip = element.querySelector(".copy-feedback-tooltip");
    if (existingTooltip) {
      existingTooltip.remove();
    }

    // 创建提示元素
    const tooltip = document.createElement("div");
    tooltip.className = `copy-feedback-tooltip ${type}`;
    tooltip.textContent = message;

    // 样式
    tooltip.style.cssText = `
            position: absolute;
            top: -30px;
            left: 50%;
            transform: translateX(-50%);
            background: ${type === "success" ? "#4CAF50" : "#f44336"};
            color: white;
            padding: 6px 12px;
            border-radius: 4px;
            font-size: 12px;
            white-space: nowrap;
            z-index: 1000;
            animation: fadeInOut 2s ease forwards;
            pointer-events: none;
        `;

    // 添加动画样式（如果不存在）
    if (!document.querySelector("#copy-feedback-styles")) {
      const style = document.createElement("style");
      style.id = "copy-feedback-styles";
      style.textContent = `
                @keyframes fadeInOut {
                    0% { opacity: 0; transform: translateX(-50%) translateY(10px); }
                    10% { opacity: 1; transform: translateX(-50%) translateY(0); }
                    90% { opacity: 1; transform: translateX(-50%) translateY(0); }
                    100% { opacity: 0; transform: translateX(-50%) translateY(-10px); }
                }
            `;
      document.head.appendChild(style);
    }

    element.style.position = "relative";
    element.appendChild(tooltip);

    // 2秒后自动移除提示
    setTimeout(() => {
      if (tooltip.parentNode) {
        tooltip.remove();
      }
    }, 2000);
  }

  createOperatorBage(qqNum) {
    // 判断管理身份
    let operatorType = "normal"; // 默认普通管理
    let badgeText = "管理";
    let badgeClass = "badge-admin";
    if (qqNum === "3875039665") {
      operatorType = "owner";
      badgeText = "群主";
      badgeClass = "badge-owner";
    } else if (FORMER_OPERATORS.includes(Number(qqNum))) {
      operatorType = "former";
      badgeText = "卸任";
      badgeClass = "badge-former";
    } else if (!(qqNum in this.InitializeEditForm.lists.operators)) {
      operatorType = "unknown";
      badgeText = "未知";
      badgeClass = "badge-unknown"
    }
    const badge = document.createElement("span");
    badge.className = `operator-badge ${badgeClass}`;
    badge.textContent = badgeText;
    const titles = {
      owner: "👑 群主",
      former: "🪦 前管理员",
      normal: "⭐️ 管理员",
      unknown: "👤 操作者",
    };
    badge.title = titles[operatorType] || "👤 操作者";
    return [badge, operatorType];
  }

  // 点击A便签元素预览图片
  previewTableImage(backendUrl, link) {

    // 防止连点
    if (link._isPreviewing) {
        return Promise.reject(new Error('操作过于频繁'));
    }
    
    link._isPreviewing = true; // 标记为“正在预览”
    // console.log('预览正在加载中，请稍候...');
    document.body.style.pointerEvents = 'none';
    document.body.style.cursor = 'wait';
    
    return new Promise(async (resolve, reject) => {
        // 将关键变量提升到Promise作用域，确保闭包内引用正确
        let blobUrl = null;
        let tempImg = null;
        let viewer = null;
        
        try {
            // 1. 下载并生成Blob URL
            blobUrl = await this.downloadFileToBlobUrl(backendUrl);
            
            // 2. 创建用于预览的临时图片元素
            tempImg = document.createElement('img');
            tempImg.src = blobUrl;
            // 增加加载和错误监听
            tempImg.onload = () => {
                // console.log('预览图片加载完成');
                document.body.style.pointerEvents = 'auto';
                document.body.style.cursor = 'default';
                // 可以在这里移除加载提示
            };
            tempImg.onerror = (e) => {
                reject(new Error('图片加载失败'));
                this.cleanupPreviewResources(viewer, blobUrl, tempImg, link);
                document.body.style.pointerEvents = 'auto';
                document.body.style.cursor = 'default';
            };
            
            // 将图片放在屏幕外（注意避免影响布局）
            tempImg.style.position = 'fixed';
            tempImg.style.left = '-9999px';
            tempImg.style.top = '0';
            document.body.appendChild(tempImg);
            
            // 3. 初始化Viewer实例
            viewer = new Viewer(tempImg, {
                inline: false,
                toolbar: false,
                navbar: false,
                title: false,
                // 使用箭头函数确保能访问到外层的资源变量
                hidden: () => {
                    // console.log('查看器已关闭，释放资源');
                    this.cleanupPreviewResources(viewer, blobUrl, tempImg, link);
                },
                // 可选：增加显示时的回调
                viewed: () => {
                    // console.log('查看器已完全显示');
                }
            });
            
            // 4. 立即显示查看器
            viewer.show();
            resolve();
            
        } catch (error) {
            console.error('预览过程出错:', error);
            // 出错时也需清理已创建的资源
            this.cleanupPreviewResources(viewer, blobUrl, tempImg, link);
            reject(error);
        }
    });
  }

  // 统一的资源清理函数
  cleanupPreviewResources(viewerInstance, blobUrl, imgElement, linkElement) {
      // 1. 销毁Viewer实例（如果存在）
      if (viewerInstance && typeof viewerInstance.destroy === 'function') {
          viewerInstance.destroy();
      }
      
      // 2. 释放Blob URL（如果存在）
      if (blobUrl && typeof URL.revokeObjectURL === 'function') {
          URL.revokeObjectURL(blobUrl);
          // console.log('Blob URL 已释放');
      }
      
      // 3. 移除临时图片元素（如果存在且仍在DOM中）
      if (imgElement && imgElement.parentNode) {
          imgElement.parentNode.removeChild(imgElement);
      }
      
      // 4. 重置链接的点击状态
      if (linkElement) {
          linkElement._isPreviewing = false;
      }
  }

  // 生成BlobUrl
  async downloadFileToBlobUrl(backendUrl) {
    try {
      // 1. 提取文件名
      const urlObj = new URL(backendUrl);
      const pathSegments = urlObj.pathname.split('/');
      const fileName = pathSegments.pop() || 'download';
      
      // 2. 下载文件
      const response = await fetch(backendUrl, {
        credentials: 'include',
        headers: { 'Accept': 'image/*, application/octet-stream' }
      });
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }
      
      // 3. 获取Blob
      const blob = await response.blob();
      
      // 4. 创建Blob URL
      const blobUrl = URL.createObjectURL(blob);
      
      // console.log(`文件已下载: ${fileName}, 大小: ${blob.size} bytes`);
      // console.log(`Blob URL: ${blobUrl}`);
      
      
      return blobUrl;
      
    } catch (error) {
      console.error('下载失败:', error);
      throw error;
    }
  }

  // 添加表格一行的数据
  addLog(match = null) {
    const count_risk = this.count_risk
    if (match) {
      const newlog = document.createElement("tr");
      newlog.className = "log";

      let processed = {}

      this.values.forEach((item, index) => {
        let field = newlog.insertCell(index);
        field.className = item;

        processed[item] = match [item]

        if (item === "mode") {
          // 添加模式对应的颜色类
          const modeClass = match[item] ? match[item] : "无";
          const mode = document.createElement("div");
          mode.classList.add(`mode-${modeClass}`, item);
          mode.textContent = match[item];
          field.className = "mode-cell";
          field.appendChild(mode);

          return;
        }

        if (item === "image") {
          let length = Object.keys(match.images_path).length;
          if (match.images_path && length > 0) {
            const entries = Object.entries(match.images_path);
            entries.forEach(([idx, path], entryIndex) => {
              // 创建链接元素
              const link = document.createElement("a");
              link.href = "javascript:void(0)";
              link.onclick = (event) => {
                event.preventDefault()
                this.previewTableImage(path, link)
              };
              // link.target = "_blank";
              link.textContent = idx;
              link.title = "查看图片";

              // 添加到单元格
              field.appendChild(link);

              // 添加分隔符
              if (entryIndex < entries.length - 1) {
                var separator = document.createTextNode(" ");
                field.appendChild(separator);
              }
            });
          } else {
            field.textContent = "无";
            field.className = "no-image";
          }
          return;
        }

        if (item === "group_id") {
          if (match[item] == "此条来自xt数据库，没有group_id") {
            field.textContent = "无";
            field.className = "no-group";

            processed[item] = ""
            // let row = field.parentElement
            // let modeTd = row.querySelector('td.mode')
            // modeTd.style.marginTop = '42.5px'
          } else {
            field.className = "group-cell";
            const group = document.createElement("div");
            group.className = item;
            field.appendChild(group);
            field = group;

            const groupText = match[item].toString();

            // 解析格式："123456789（群名称）" 或纯数字
            const matchResult = groupText.match(
              /^(\d+)(?:\s*[（(](.+?)[）)])?$/,
            );

            processed[item] = {}

            if (matchResult) {
              const qqNum = matchResult[1];
              const groupName = matchResult[2];

              processed[item]["group_id"] = parseInt(qqNum)
              processed[item]["nickname"] = groupName

              if (qqNum == 833970143) {
                field.dataset.groupType = "large";
              }
              if (qqNum == 1048699506) {
                field.dataset.groupType = "server";
              }
              if (qqNum == 1057699431) {
                field.dataset.groupType = "core";
              }
              if (qqNum == 1058185958) {
                field.dataset.groupType = "moderator";
              }
              if (qqNum == 702683488) {
                field.dataset.groupType = "notice";
              }
              if (qqNum == 963462616) {
                field.dataset.groupType = "operator";
              }
              if (qqNum == 607933097) {
                field.dataset.groupType = "doujin";
              }

              // 创建结构化显示
              const container = document.createElement("span");
              container.className = "group-info";
              const numberSpan = document.createElement("span");
              numberSpan.className = "group-number";
              numberSpan.textContent = qqNum;

              container.appendChild(numberSpan);

              if (groupName) {
                const nameSpan = document.createElement("span");
                nameSpan.className = "group-name";
                nameSpan.textContent = groupName;
                container.appendChild(nameSpan);
              }
              field.appendChild(container);

              // 设置头像
              const avatarUrl = `https://curator.ip-ddns.com:8000/api/files/images/groups/${qqNum}.jpg`;

              // 预加载头像
              this.preloadAvatar(field, avatarUrl);
            } else {
                // 如果格式不匹配，直接显示文本
                field.textContent = groupText;
                field.classList.add("no-avatar");

                processed[item]["group_id"] = groupText
                processed[item]["nickname"] = ""
            }
          }
          return;
        }

        if (item === "duration") {
          const span = document.createElement("span")
          span.textContent = this.formatDuration(match[item]);
          field.appendChild(span)
          return;
        }

        if (item === "operator") {
          const operatorText = match[item].toString();

          // 解析格式："123456789（管理名称）" 或纯数字
          const matchResult = operatorText.match(
            /^(\d+)(?:\s*[（(](.+?)[）)])?$/,
          );

          processed[item] = {}

          if (matchResult) {
            const qqNum = matchResult[1];
            const operatorName = matchResult[2];

            processed[item]["operator"] = parseInt(qqNum)
            processed[item]["nickname"] = operatorName

            // 创建容器
            const container = document.createElement("div");
            container.className = "operator-info";

            // 添加身份徽章
            const list = this.createOperatorBage(qqNum);
            const badge = list[0];
            const operatorType = list[1];
            container.appendChild(badge);

            // QQ号显示
            const numberSpan = document.createElement("span");
            numberSpan.className = "operator-number";
            numberSpan.textContent = qqNum;
            this.addCopyToClipboard(numberSpan);
            container.appendChild(numberSpan);

            // 昵称显示（如果有）
            if (operatorName) {
              const nameSpan = document.createElement("span");
              nameSpan.className = "operator-name";
              nameSpan.textContent = operatorName;
              this.addCopyToClipboard(nameSpan);
              container.appendChild(nameSpan);
            }

            // 设置容器数据属性，方便CSS选择
            container.dataset.operatorType = operatorType;

            field.appendChild(container);
          } else {
            field.textContent = operatorText;

            processed[item]["operator"] = operatorText
            processed[item]["nickname"] = ""
          }
          return;
        }

        if (item === "target") {
          let container
          container, match, processed = this.createTarget(item, match, processed, count_risk)
          field.appendChild(container)
          return;
        }

        const span = document.createElement("span")
        span.textContent = match[item];
        field.appendChild(span)

        // field.textContent = match[item];
      });
      
      // 数据储存在data方便表单读取
      newlog.dataset.match = JSON.stringify(processed)
      newlog.dataset.original = JSON.stringify(match)
      newlog.dataset.log_id = match["id"]

      // 增加删除log按钮
      const remove_btn = document.createElement("button")
      remove_btn.className = "remove-log-btn"
      remove_btn.type = "button"
      remove_btn.title = "删除记录"
      newlog.appendChild(remove_btn)

      return newlog
    }
  }

  createTarget(item, match, processed, count_risk) {
    const targetText = match[item].toString();

    // 解析格式："123456789（目标名称）" 或纯数字
    const matchResult = targetText.match(
      /^(\d+)(?:\s*[（(](.+?)[）)])?$/,
    );

    processed[item] = {}
    const container = document.createElement("div");

    if (matchResult) {
      const qqNum = matchResult[1];
      const targetName = matchResult[2];

      processed[item]["target"] = parseInt(qqNum)
      processed[item]["nickname"] = targetName

      // 获取用户数据
      let userData = count_risk[qqNum] || {
        count: 1,
        risk: 0.5,
        state: "存活",
      };
      const count = userData.count;
      const risk = userData.risk;
      const state = userData.state;

      // 计算风险等级
      let riskLevel = "low";
      let riskLabel = "低风险";
      if (risk > 2) {
        riskLevel = "high";
        riskLabel = "高风险";
      } else if (risk > 1) {
        riskLevel = "medium";
        riskLabel = "中风险";
      }

      // 获取状态对应的颜色和图标
      const stateConfig = {
        存活: { class: "alive", icon: "🟢", color: "#4CAF50" },
        已踢出: { class: "kicked", icon: "🟡", color: "#FF9800" },
        已拉黑: { class: "banned", icon: "🔴", color: "#F44336" },
      };
      const stateInfo = stateConfig[state] || stateConfig["存活"];

      // 创建容器
      container.className = "target-info";
      container.dataset.riskLevel = riskLevel;
      container.dataset.state = stateInfo.class;

      // 风险徽章
      const riskBadge = document.createElement("div");
      riskBadge.className = `target-risk-badge risk-${riskLevel}`;
      riskBadge.innerHTML = `
                      <span class="risk-icon">${riskLevel === "high" ? "⚠️" : riskLevel === "medium" ? "🔶" : "🔵"}</span>
                      <span class="risk-text">${riskLabel}</span>
                      <span class="risk-score">${risk.toFixed(1)}</span>
                  `;
      container.appendChild(riskBadge);

      // 主要信息区域
      const mainInfo = document.createElement("div");
      mainInfo.className = "target-main";

      // QQ号
      const numberSpan = document.createElement("span");
      numberSpan.className = "target-number";
      numberSpan.textContent = qqNum;
      this.addCopyToClipboard(numberSpan);
      mainInfo.appendChild(numberSpan);

      // 昵称（如果有）
      if (targetName) {
        const nameSpan = document.createElement("span");
        nameSpan.className = "target-name";
        nameSpan.textContent = targetName;
        this.addCopyToClipboard(nameSpan);
        mainInfo.appendChild(nameSpan);
      }

      // 状态指示器
      const stateIndicator = document.createElement("span");
      stateIndicator.className = `target-state state-${stateInfo.class}`;
      stateIndicator.textContent = `${stateInfo.icon} ${state}`;
      stateIndicator.style.setProperty("--state-color", stateInfo.color);
      mainInfo.appendChild(stateIndicator);

      container.appendChild(mainInfo);

      // 悬停提示
      container.title = `QQ: ${targetText}\n违规记录: ${count} 条\n风险值: ${risk.toFixed(1)} (${riskLabel})\n状态: ${state}`;

      return container, match, processed
    } else {
      container.textContent = targetText;

      processed[item]["target"] = targetText
      processed[item]["nickname"] = ""
      return container, match, processed
    }
  }

  // 删除log
  removeLog(target) {
      
    // 确认信息
    Swal.fire({
      title: YAML["delete_confirm"],
      text: YAML["delete_confirm2"],
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#d33',
      cancelButtonColor: '#3085d6',
      confirmButtonText: '是',
      cancelButtonText: '否',
      customClass: {
        popup: 'custom-swal-popup'
      }
    }).then(async (result) => {
      if (result.isConfirmed) {
        try {
          const newlog = target.parentElement
          const logId = newlog.dataset.log_id

          // 发送删除请求到后端
          const response = await fetch("https://curator.ip-ddns.com:8000/api/delete", {
            method: 'POST',
            credentials: 'include',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              id: logId
            })
          });

          const result = await response.json()
          const success = result.success
          const message = result.message

          if (success === true) {
            
            // 更新risk
            Object.entries(response.risk).forEach(([key, value]) => {this.InitializeTable.count_risk[key] = value})

            const targetSpan = document.querySelectorAll('span.target-number')
            targetSpan.forEach((span) => {
              this.updateRisk(response.risk, span)
            })

            // 播放删除动画并等待播放完后删除
            newlog.classList.add('tr-removing');
            setTimeout(() => {
              newlog.remove();
              
              // 显示成功提示
              Swal.fire({
                title: YAML["delete_success"],
                text: message,
                icon: 'success',
                timer: 1500,
                showConfirmButton: false
              });

            }, 600);

          } else {

            // 显示失败提示
            Swal.fire({
              title: YAML["delete_error"],
              text: message,
              icon: 'error',
              timer: 1500,
              showConfirmButton: false
            });
          }
        } catch (error) {
          console.error('删除请求错误:', error);
          
          // 显示报错提示
          Swal.fire({
            title: YAML["delete_error"],
            text: `${YAML["delete_error2"]}${error.message}`,
            icon: 'error',
            timer: 1500,
            showConfirmButton: false
          });
        }
      }
    });
  }

  //渲染页面
  renderPage(logsData, count_risk) {
    this.count_risk = count_risk
    const container = document.getElementById('logs-container');
    const brands = navigator.userAgent

    // IE浏览器手动取消监听避免内存泄漏风险
    if (brands.indexOf('MSIE ') > -1) {
        const old_logs = document.querySelectorAll(".log")
        old_logs.forEach((item) => {
            this.InitializeEditForm.removeClickEvent(item)
            item.remove()
        })
    }

    // 删除残留log
    container.innerHTML = '';
    const fragment = document.createDocumentFragment();

    // 添加log
    if (logsData && logsData.length > 0) {
      logsData.forEach((item) => {
        const newlog = this.addLog(item);
        fragment.appendChild(newlog)
      });

      container.appendChild(fragment)
    }
    // document.querySelectorAll('#logs td.mode').forEach((cell, i) => {
    // console.log(`第${i+1}行:`, cell.offsetHeight, cell.offsetTop)
    // })
    // document.querySelectorAll('#logs tbody tr').forEach((row, rowIndex) => {
    //     const cells = row.querySelectorAll('td')
    //     console.log(`第${rowIndex+1}行各单元格高度:`)
    //     cells.forEach((cell, cellIndex) => {
    //         console.log(`  列${cellIndex}: ${cell.offsetHeight}px`)
    //     })
    // })
  }

}

class InitializeEditForm {
  constructor(values, InitializeTable) {
    this.values = values
    this.InitializeTable = InitializeTable

    // 表单参数不合法的提示词写进了风格文件
    this.style = YAML

    // 上一个log行元素
    this.lastlog = null

    // 统计表单每个input是否合法
    this.validationStates = new Map()

    // 检查输入值是否改变
    this.fieldchange = new Map()

    // 来自logs系统风格文件的列表,用于检测表单参数是否合法
    this.lists = {
      "modes": CONFIG.modes,
      "group_ids": CONFIG.group_ids,
      "operators": CONFIG.operators
    }
    
    this._lists = {
      "modes_nicknames": CONFIG.modes_nicknames,
      "group_ids_nicknames": CONFIG.group_ids_nicknames,
      "operators_nicknames": CONFIG.operators_nicknames
    }

    CONFIG.duration_errors[0] = this.style.duration_error1
    this.duration_errors = CONFIG.duration_errors

    // 初始化表单监听
    this.initFieldCheck()
  }
  
  // 点击新增记录按钮时打开编辑表单
  initAddForm () {
    const target = document.getElementById("test_log")

    // 显示编辑表单
    const form = document.getElementById("edit")
    document.getElementById("form-overlay").className = "active"

    if (this.lastlog && this.lastlog === target) {
      return
    } else {
      this.lastlog = target
      this.validationStates.clear()
      this.fieldchange.clear()
      this.values.forEach((item) => this.validationStates.set(item, false))
      this.validationStates.set("id", true)
      this.validationStates.set("duration", true)
      this.checkFieldStates(false)
    }

    let match = {}
    
    this.initForm(match)
  }

  // 点击每行log时打开编辑表单
  initEditForm (event) {

    let match
    let target

    // 仅限表体行和表体单元格的点击事件
    if (event.target.tagName == 'TR') {
      target = event.target
      match = JSON.parse(target.dataset.match)
    } else if (event.target.tagName == 'TD') {
      target = event.target.parentElement
      match = JSON.parse(target.dataset.match)
    } else if (event.target.tagName == 'BUTTON' && event.target.className == "remove-log-btn") {
      this.InitializeTable.removeLog(event.target)
      return
    } else {
      return
    }

    // 显示编辑表单
    document.getElementById("form-overlay").className = "active"

    if (this.lastlog && this.lastlog === target) {
      return
    } else {
      this.lastlog = target
      this.validationStates.clear()
      this.fieldchange.clear()
      this.checkFieldStates(true)
    }
    
    this.initForm(match)
  }

  // 将指定内容预输入输入栏
  initForm (match) {
    
    const form = document.getElementById("edit")
    this.values.forEach((item) => {
      const container = form.querySelector(`div[id="${item}"]`)
      if (container) {
          const input = container.querySelector(`input[name="${item}"]`)

          if (item === "id") {
            if (!match[item]) {
              input.title = this.style.id_disabled
            } else {
              input.title = ""
            }
            input.value = match[item] || ""
            return
          }

          // 带昵称的预输入昵称，旧的log可能没有群聊QQ，则群聊QQ输入栏允许为空
          if (item === "target" || item === "group_id" || item === "operator") {
            let nickname = container.querySelector(`input[name="${item}_nickname"]`)
            if (match[item]) {
              nickname.value = match[item]["nickname"] || ""
              input.value = match[item][item]
              input.required = true
              nickname.required = (item === "target") ? false : true
            } else {
              input.value = ""
              nickname.value = ""
              if (match["id"]) {
                input.required = false
                nickname.required = false
              } else {
                input.required = true
                nickname.required = (item === "target") ? false : true
              }
            }
            return
          }

          // 模式为禁言时预输入时长
          if (item === "duration") {
            const mode = document.querySelector(`input[name="mode"]`)
            if (mode.value === "禁言") {
              input.value = match[item] || ""
              input.title = ""
              input.required = true
              input.readOnly = false
            } else {
              input.value = ""
              input.title = this.style.duration_disabled
              input.required = false
              input.readOnly = true
            }
            return
          }

          // 预输入预览图片
          if (item === "image") {
            const imagePreview = container.querySelector("div[id='imagePreview']")
            imagePreview.innerHTML = ""
            let ifempty = true
            if (match.images_path) {
              Object.values(match.images_path).forEach(path => {
                this.previewImage(path);
                ifempty = false
              });
            }
            if (ifempty) {
              imagePreview.textContent = this.style.image_error
              imagePreview.className = "empty"
            }
            return
          }

          input.value = match[item] || ""
      }
    })
  }

  // 初始化表单监听
  initFieldCheck() {

    const container = document.getElementById('logs-container');
    const form = document.getElementById("edit")
    const overlay = document.getElementById("form-overlay")

    // 点击新增记录按钮，打开编辑表单
    const add_btn = document.getElementsByClassName("add-record-btn")[0]
    add_btn.addEventListener("click", () => this.initAddForm())

    // 点击表格行和单元格，打开编辑表单
    container.addEventListener("click", (event) => this.initEditForm(event))

    // 取消回车提交表单
    form.addEventListener('keydown', function(event) {
      if (event.key === 'Enter' && event.target.tagName === "INPUT") {
          event.preventDefault();
          event.stopPropagation();
      }
    });

    // 通过事件委托监听失焦事件
    form.addEventListener("focusout", (event) => this.initFormInputFocusout(event))

    // 图片上传需要单独进行事件委托
    form.addEventListener("input", (event) => {
      let input = event.target
      if (input.name && input.name === "image") {
        const re = this.checkimage(input)
        this.validationStates.set("image", re)
        this.checkFieldStates(re)
      }
    })

    // 通过事件委托监听点击事件
    form.addEventListener("click", async (event) => {

      // 阻止表单内部点击事件向父元素冒泡
      event.stopPropagation()

      const target = event.target

      // 点击按钮关闭表单
      if (target.tagName === "BUTTON" && target.id === "close-form" && this.validationStates.get("upload") !== false) {
        event.preventDefault()
        overlay.className = "hide"
        this.lastlog = null
      } else if (target.tagName === "INPUT" && target.id === "submit") {
        event.preventDefault()
        await this.handleSubmit(target)
      }
    })

    // 点击表单以外的地方关闭表单
    overlay.addEventListener("click", () => {
      if (this.validationStates.get("upload") !== false) {
        overlay.className = "hide"
      }
    })

    // 初始化图片预览区域的排序功能
    new Sortable(document.getElementById('imagePreview'), {
      animation: 150,
      forceFallback: true,
      // onEnd: function (evt) {
      //   console.log('图片位置已变更，从索引', evt.oldIndex, '移动到', evt.newIndex);
      // }
    });

    // 根据log系统风格文件的列表添加datalist
    for (const [key, list] of Object.entries(this.lists)) {
      const datalist = document.querySelector(`datalist[id="${key}"]`)
      if (datalist) {
        if (key === "modes") {
          for (const value of list) {
            const option = document.createElement("option")
            option.value = value
            datalist.appendChild(option)
          }
        } else {
          const nickname_datalist = document.querySelector(`datalist[id="${key}_nicknames"]`)
          for (const [qq, nickname] of Object.entries(list)) {
            const qq_option = document.createElement("option")
            qq_option.value = qq
            datalist.appendChild(qq_option)
            const nickname_option = document.createElement("option")
            nickname_option.value = nickname
            nickname_datalist.appendChild(nickname_option)
          }
        }
      }
    }

    // 监听屏幕尺寸变化，同步电流边框和页码栏宽度同步
    window.addEventListener('resize', () => {
      this.updateAnimationValues();
      window.pageButtion.syncPageWidth();
    });
  }

  // 初始化输入栏监听
  initFormInputFocusout (event) {
    let input = event.target

    // 只监听input
    if (input.tagName === "INPUT" && input.name !== "image") {

      // 防止循环回调
      if (input.dataset.blurred === "true") {
        input.dataset.blurred = "false"
        return
      }
      
      // 获取修改前表单值并更新Map
      let item = input.name
      const value_old = this.fieldchange.get(item)
      const value = input.value
      this.fieldchange.set(item, value)

      // 根据不同input执行不同检测函数
      let re
      if (item === "operator" || item === "group_id") {
        const nickname = input.parentElement.querySelector(`input[name="${item}_nickname"]`)
        re = this["checkqq"](input, nickname)
      } else if (item === "operator_nickname" || item === "group_id_nickname") {
        item = item.slice(0, -9)
        const nickname = input
        input = nickname.parentElement.querySelector(`input[name="${item}"]`)
        re = this["checknickname"](input, nickname)
      } else {
        const fun = this['check' + item]
        if (!fun) {
          return
        }
        re = this['check' + item](input)
      }

      // 昵称修改无需提示
      if (re === null) {
        return

      // 如果表单值不合法，且没有更改，取消提示并失焦————只提示一次避免用户无法失焦表单
      } else if (re === false && value_old === value) {
        input.setCustomValidity('')
        input.dataset.blurred = "true"
        input.blur()

      // 更新当前输入值合法与否，并检查输入值是否全部合法
      } else {
        this.validationStates.set(item, re)
        this.checkFieldStates(re)
      }
    }
  }

  // 电流边框宽高同步
  updateAnimationValues() {
    const card = document.querySelector(".card");
    if (!card) return;

    const PX_PER_SEC = 100;
    const SIZE_FACTOR = 1.4;

    const { width, height } = card.getBoundingClientRect();

    const filterHeight = height * SIZE_FACTOR;
    const durY = filterHeight / PX_PER_SEC;
    const animateDy1 = document.getElementById("animate-dy-1");
    const animateDy2 = document.getElementById("animate-dy-2");
    if (animateDy1) {
      animateDy1.setAttribute("values", `${filterHeight}; 0`);
      animateDy1.setAttribute("dur", `${durY}s`);
    }
    if (animateDy2) {
      animateDy2.setAttribute("values", `0; -${filterHeight}`);
      animateDy2.setAttribute("dur", `${durY}s`);
    }

    const filterWidth = width * SIZE_FACTOR;
    const durX = filterWidth / PX_PER_SEC;
    const animateDx1 = document.getElementById("animate-dx-1");
    const animateDx2 = document.getElementById("animate-dx-2");
    if (animateDx1) {
      animateDx1.setAttribute("values", `${filterWidth}; 0`);
      animateDx1.setAttribute("dur", `${durX}s`);
    }
    if (animateDx2) {
      animateDx2.setAttribute("values", `0; -${filterWidth}`);
      animateDx2.setAttribute("dur", `${durX}s`);
    }
  }

  // 检查时长，逻辑和log系统的一样
  checkduration(input) {
    const value = input.value
    console.log(value)
    if (value !== "") {
      const pattern = /^\d+(\.\d)?[hsmdMw]$/;
      
      let error = null
      if (!pattern.test(String(value))) {
          error = 1
      } else {
        const unit = value.slice(-1);
        const number = parseFloat(value.slice(0, -1));

        // 检查时间是否合法，比如不能有25h、0.5s
        if ((unit === "m" || unit === "s") && (number < 1 || number > 60)) {
            error = 2
        } else if (unit === "h" && (number < 1 || number > 720)) {
            error = 3
        } else if (unit === "d" && (number < 1 || number > 30)) {
            error = 4
        } else if (unit === "w" && (number < 1 || number > 4.28)) {
            error = 6
        } else if (unit === "M" && number !== 1) {
            error = 5
        }
      }
      if (error) {
        input.setCustomValidity(this.duration_errors[error-1]);
        input.reportValidity();
        return false
      } else {
        input.setCustomValidity('')
        return true
      }
      
    }
    input.setCustomValidity(this.style.duration_error);
    input.reportValidity();
    return false
  }

  // 检查目标QQ长度是否合法，检查是否在群内的功能只能在后端进行
  checktarget (input) {
    if (input.value.length < 5 || input.value.length > 11) {
      input.setCustomValidity(this.style.qq_len_error);
      input.reportValidity();
      return false
    } else {
      input.setCustomValidity('')
      return true
    }
  }

  // 原因不能是纯数字
  checkreason (input) {
    if (input.value !== "" && !Number(input.value)) {
      input.setCustomValidity('')
      return true
    } else {
      input.setCustomValidity(this.style.reason_error);
      input.reportValidity();
      return false
    }
  }

  // 检查群聊和管理员QQ是否合法，是否在可选范围内
  checkqq (input, input_nickname) {
    const nickname = this.lists[input.name+"s"][input.value]
    if (input.value !== "") {

      // 检查目标QQ长度是否合法
      if (input.value.length < 5 || input.value.length > 11) {
        input.setCustomValidity(this.style.qq_len_error);
        input.reportValidity();
        return false
      } else {

        // 检查是否存在对应昵称
        if (nickname) {
          input_nickname.value = nickname
          input.setCustomValidity('')
          return true
        } else if (input_nickname.value === "") {
          input.setCustomValidity(this.style.qq_error);
          input.reportValidity();
          return false
        } else {
          return true
        }
      }

    // 如果输入栏为空，检查是否要求强制填写此值
    } else {
      if (input.required) {
        return false
      } else {
        input.setCustomValidity('')
        return true
      }
    }
  }

  // 检查昵称是否有匹配的QQ
  checknickname (input, input_nickname) {
    const _list = this._lists[input.name + "s_nicknames"]

    // 输入值大于1才进行匹配
    if (input_nickname.value.length <= 1) {
      return null
    }

    // 输入值为某个昵称开头的直接进行匹配
    let qq = null
    let qqs = []
    let ifqq = false
    for (const key of Object.keys(_list)) {
      if (key.startsWith(input_nickname.value)) {
        qq = _list[key]
        ifqq = false
        break
      }
      if (key.includes(input_nickname.value)) {
        qqs.push(key)
        ifqq = true
      }
    }

    // 不是某个昵称开头值则选择第一个包含输入值的昵称
    if (ifqq) {
      qq = qqs[0]
    }

    if (qq) {
      input.value = qq
      input_nickname.value = this.lists[input.name+"s"][qq]
      return this.checkqq(input, input_nickname)
    } else {
      return null
    }
  }

  // 检查模式是否可选，或是某个昵称
  checkmode (input){
    const mode = this._lists["modes_nicknames"][input.value]
    if (input.value !== "" && mode) {
      input.setCustomValidity('')
      input.value = mode

      // 检查模式是不是禁言，调整时长输入栏状态
      const duration = input.parentElement.parentElement.querySelector("input[name='duration']")
      if (input.value === "禁言") {
        duration.value = this.fieldchange.get("duration") || ""
        this.validationStates.set("duration", false)
        duration.title = ""
        duration.required = true
        duration.readOnly = false
      } else {
        this.fieldchange.set("duration", duration.value || "")
        duration.value = ""
        this.validationStates.set("duration", true)
        duration.title = this.style.duration_disabled
        duration.required = false
        duration.readOnly = true
      }
      return true
    } else {
      input.setCustomValidity(this.style.mode_error);
      input.reportValidity();
      return false
    }
  }

  // 检查时间输入值是否在范围内
  checktime (input) {
      const time = this.formatToDatetimeLocal()
      const limit = "2025-05-12T00:00:00"

      if (time < input.value) {
          input.blur();
          input.setCustomValidity(`${this.style.time_error} ${time.replace('T', ' ')}`);
          input.reportValidity();
          return false
      } else if (input.value < limit) {
          input.blur();
          input.setCustomValidity(`${this.style.time_error2} ${limit.replace('T', ' ')}`);
          input.reportValidity();
          return false
      } else {
          input.setCustomValidity('')
          return true
      }
    }

  // 生成符合datetime-local的当前时间
  formatToDatetimeLocal(data = null) {
      const date = data || new Date()
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      const hours = String(date.getHours()).padStart(2, '0');
      const minutes = String(date.getMinutes()).padStart(2, '0');
      const seconds = String(date.getSeconds()).padStart(2, '0');
      
      return `${year}-${month}-${day}T${hours}:${minutes}:${seconds}`;
  }

  // 检查图片格式是否被允许
  checkimage (input) {
    const files = input.files;

    const allowedTypes = [
        'image/jpeg',      // .jpg, .jpeg
        'image/png',       // .png
        'image/gif',       // .gif
        'image/webp',      // .webp
        'image/svg+xml',   // .svg
        'image/bmp',       // .bmp
        'image/tiff'       // .tiff
    ];

    let message = ""
    let ifpre = []
    for (const file of files) {
      if (!allowedTypes.includes(file.type)) {
        if (!message) {
          message = `${this.style.image_error2}：${file.name}`
        } else {
          message = `${message}、${file.name}`
        }
        continue
      }
      ifpre.push(this.previewImage(file));
    }
    if (message) {
      showNotification(message);
    }
    input.value = ""

    if (ifpre.includes(true)) {
      return true
    } else {
      return false
    }
  }

  // 加载图片文件
  previewImage(file) {
    if (file instanceof File) {
      const reader = new FileReader();
      
      reader.onload = (e) => {
        this.createPreview(e.target.result)
      };
      
      reader.readAsDataURL(file); // 读取文件为DataURL
    } else if (typeof file === 'string') {
        this.createPreview(file)
    } else {
      showNotification(`${this.style.image_error3}typeof file`);
      return false
    }
    return true
  }

  // 创建预览图片
  createPreview(e) {
    const imagePreview = document.getElementById('imagePreview')
    if (imagePreview.children.length === 0) {
      imagePreview.textContent = ""
      imagePreview.className = "full"
    }
    const previewContainer = document.createElement("div");
    previewContainer.className = "preview-item";

    // previewContainer.draggable = true;

    const previewImg = document.createElement("img");
    previewImg.src = `${e}`
    previewImg.alt = "违规图片"
    previewImg.className = "preview-image"
    previewContainer.appendChild(previewImg)

    const removeBtn = document.createElement("button");
    removeBtn.type = "button"
    removeBtn.className = "remove-btn"
    removeBtn.innerHTML = "&times;"
    removeBtn.title = "删除图片"
    previewContainer.appendChild(removeBtn)
    
    imagePreview.appendChild(previewContainer)

    previewImg.addEventListener('click', () => {

    });

    // 删除按钮点击事件
    removeBtn.addEventListener('click', () => {
        previewContainer.remove();

        // 没有图片则禁止提交
        if (imagePreview.children.length === 0) {
          imagePreview.textContent = this.style.image_error
          imagePreview.className = "empty"
          let re = false
          this.validationStates.set("image", re)
          this.checkFieldStates(re)
        }
    });
    
  }

  // 检查输入值是否全部合法
  checkFieldStates(re) {
    const submit = document.getElementById("submit")
    if (re === false) {
      submit.disabled = true
    } else {
      const allValid = Array.from(this.validationStates.values()).every(state => state === true)
      submit.disabled = !allValid;
    }
  }

  // 输入值传给后端
  async handleSubmit (submit) {
    
    document.body.style.cursor = 'wait'
    this.validationStates.set("upload", false)
    this.checkFieldStates(false)
    document.getElementById("close-form").disabled = true

    const match = this.packMatch(submit.parentElement)
    
    const response = await fetch("https://curator.ip-ddns.com:8000/api/edit", {
      method: "POST",
      credentials: 'include',
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({"match": match}),
    });

    this.handleResponse(await response.json())
  }

  // 更新risk值
  updateRisk (risk, span) {
    if (span.textContent in risk) {
      const tr = span.closest('tr')
      const old_container = span.closest('div.target-info')

      let match = JSON.parse(tr.dataset.original)
      let processed = JSON.parse(tr.dataset.match)
      let container
      const item = "target"
      container, match, processed = this.createTarget(item, match, processed, risk)

      tr.dataset.original = JSON.stringify(match)
      tr.dataset.match = JSON.stringify(processed)
      old_container.replaceWith(container)
      this.InitializeTable.count_risk[key] = value
    }
  }
  
  // 处理提交表单后，后端发来的返回值
  handleResponse (response) {
    try {

      // 更新表单状态
      this.validationStates.set("upload", true)
      this.checkFieldStates(true)
      document.getElementById("close-form").disabled = false
      document.body.style.cursor = 'default'

      // 更改成功则关闭表单，并更新该条log
      if (response.success === true) {
        showNotification(response.message, 5)
        
        const formOverlay = document.getElementById("form-overlay");
        formOverlay.className = "hide";
        
        // 更新risk
        Object.entries(response.risk).forEach(([key, value]) => {this.InitializeTable.count_risk[key] = value})

        const targetSpan = document.querySelectorAll('span.target-number')
        targetSpan.forEach((span) => {
          this.updateRisk(response.risk, span)
        })

        // 创建新行
        const newRow = this.InitializeTable.addLog(response.match);

        // 添加模式加入到表格
        if (response.action === "add") {
          const tbody = document.getElementById("logs-container")
          this.lastlog = newRow
          tbody.prepend(newRow)

        // 编辑模式替换旧行
        } else {
          this.lastlog.replaceWith(newRow);
        }

        // 删除上一个更新log效果
        const updated = document.getElementsByClassName("card")[0]
        if (updated) {
          updated.classList.remove("card")
          const elements = document.getElementsByClassName("card__layer");
          const fragment = document.createDocumentFragment();
          Array.from(elements).forEach(el => fragment.appendChild(el));
        }

        // 给更新的log添加电流边框
        const card1 = document.createElement("div")
        card1.className = "card__layer card__layer--main"
        newRow.classList.add("card");
        newRow.appendChild(card1)
        this.updateAnimationValues()

      // 更改失败则显示失败原因
      } else {
        showNotification(response.message)
        console.log(response.message)
      }
    } catch (error) {
      console.log(error)
      showNotification(`${this.style.response_error}${error}`)
    }
  }

  // 打包传给后端的数据
  packMatch (form) {
    const match = {}
    this.values.forEach((item) => {
      const container = form.querySelector(`div[id="${item}"]`)
      if (container) {

        // 直接读取输入栏的内容
        const input = container.querySelector(`input[name="${item}"]`)

        // 有昵称的进行合并
        if (item === "target" || item === "group_id" || item === "operator") {
          match[item] = {}
          match[item][item] = input.value || ""
          match[item][`nickname`] = container.querySelector(`input[name="${item}_nickname"]`).value || ""

        // 图片地址打包
        } else if (item === "image") {
          const imagePreview = document.getElementById("imagePreview")
          match["images"] = {}
          match["images"]["data_url"] = {}
          match["images"]["static"] = {}
          for (const [index, child] of Array.from(imagePreview.children).entries()) {
            const img = child.querySelector("img")

            // 刚上传的base64的url和已经保存的进行分流
            if (img.src.startsWith("data:image/")) {
              match["images"]["data_url"][index+1] = img.src

            // 删掉url前缀，只保留路径+文件名
            } else {
              match["images"]["static"][index+1] = String(img.src).split('/').pop()
            }
          }

        } else if (item === "time") {
          match[item] = input.value.replace("T", " ")

        } else {
          match[item] = input.value || ""
        }
      }
    })
    return match
  }
}

// 初始化页码按钮
class InitializePageButton {
  constructor() {}

  //生成翻页按钮
  createPageButton(page = 1, maxpage = 1) {
    
    // 删除旧的页码
    page = parseInt(page);
    const oldButtons = document.querySelectorAll(".page_button");
    oldButtons.forEach((button) => button.remove());
    const oldDots = document.querySelectorAll(".page-dots");
    oldDots.forEach((dot) => dot.remove());

    const nextBtn = document.getElementById("nextBtn");
    const prevBtn = document.getElementById("prevBtn");
    if (page == 1) {
      prevBtn.disabled = true;
    } else {
      prevBtn.disabled = false;
    }
    if (page == maxpage) {
      nextBtn.disabled = true;
    } else {
      nextBtn.disabled = false;
    }

    // 生成页码按钮
    for (let index = 1; index <= maxpage; index++) {
      // 处理省略号逻辑
      if (maxpage > 10) {
        if (page > 6 && index == 4) {
          // 添加前省略号
          let dots = document.createElement("span");
          dots.innerText = "...";
          dots.className = "page-dots";
          nextBtn.parentNode.insertBefore(dots, nextBtn);
          index = page - 3;
          continue;
        }

        if (index == page + 3 && maxpage - page > 5) {
          // 添加后省略号
          let dots = document.createElement("span");
          dots.innerText = "...";
          dots.className = "page-dots";
          nextBtn.parentNode.insertBefore(dots, nextBtn);
          index = maxpage - 3;
          continue;
        }

        // 显示逻辑：始终显示首尾3页和当前页前后2页
        // if (index > 3 &&
        //     index < page - 2 &&
        //     index < maxpage - 2) {
        //     continue
        // }

        // if (index > page + 2 &&
        //     index < maxpage - 2 &&
        //     index > 3) {
        //     continue
        // }
      }

      // 创建页码按钮
      let newButton = document.createElement("button");
      newButton.innerText = index.toString();
      newButton.className = "page_button";

      if (page !== index) {
        newButton.onclick = () => this.pageButtonOnClick(newButton);
      } else {
        newButton.disabled = true;
        newButton.classList.add("active");
      }

      nextBtn.parentNode.insertBefore(newButton, nextBtn);
    }
  }

  // 点击翻页按钮
  pageButtonOnClick(th) {
    if (th) {
      var page = th.textContent;
    } else {
      var page = parseInt(this.textContent);
    }
    if (page == "上一页") {
      page = parseInt(localStorage.getItem("currentPage"));
      page = page - 1;
    }
    if (page == "下一页") {
      page = parseInt(localStorage.getItem("currentPage"));
      page = page + 1;
    }
    localStorage.setItem("currentPage", page);
    getLogFromBackend().then(() => {
      // console.log('数据加载完成');
    });
  }
  
  // 同步页码栏的宽度
  syncPageWidth() {
    const table = document.getElementById("logs");
    const page = document.getElementById("page");
    const title = document.getElementById("icon-title");

    // 获取表格的实际宽度
    const tableWidth = table.offsetWidth;

    // 设置分页与表格同宽
    page.style.width = tableWidth + "px";
    title.style.width = tableWidth - 42 + "px";
  }
}

// 初始化上限选择器
class InitializeLimitSelector {
  constructor() {
    this.limitOptions = [10, 30, 50, 80, 100, 500];
    this.currentLimit = parseInt(localStorage.getItem("limit")) || 10;
    this.init();
  }

  init() {
    // 创建DOM元素
    this.createSelector();

    // 绑定事件
    this.bindEvents();

    // 初始化显示
    this.updateCurrentLimit();
    this.generateOptions();
  }

  createSelector() {
    // 如果已经存在，先移除
    const existing = document.getElementById("limitSelector");
    if (existing) existing.remove();

    // 创建选择器容器
    const limitSelector = document.createElement("div");
    limitSelector.id = "limitSelector";

    // 当前选择显示框
    const currentBox = document.createElement("div");
    currentBox.id = "limitCurrent";

    currentBox.innerHTML = `
            <span>每页:</span>
            <strong id="currentLimitValue">${this.currentLimit}</strong>
            <span class="limit-arrow">▲</span>
        `;

    // 下拉选项框
    const optionsBox = document.createElement("div");
    optionsBox.id = "limitOptions";

    limitSelector.appendChild(currentBox);
    limitSelector.appendChild(optionsBox);

    // 插入到#page的最前面
    const pageDiv = document.getElementById("page");
    pageDiv.insertBefore(limitSelector, pageDiv.firstChild);
  }

  generateOptions() {
    const optionsBox = document.getElementById("limitOptions");
    optionsBox.innerHTML = "";

    this.limitOptions.forEach((limit) => {
      const option = document.createElement("div");
      option.className = "limit-option";
      option.dataset.limit = limit;
      option.textContent = limit;
      if (limit === this.currentLimit) {
        option.classList.add("selected");
      }
      option.addEventListener("click", () => this.selectLimit(limit));
      optionsBox.appendChild(option);
    });
  }

  updateCurrentLimit() {
    const currentValue = document.getElementById("currentLimitValue");
    if (currentValue) {
      currentValue.textContent = this.currentLimit;
    }

    // 高亮当前选项（如果有的话）
    document.querySelectorAll(".limit-option").forEach((option) => {
      const limit = parseInt(option.dataset.limit);
      option.classList.toggle("selected", limit === this.currentLimit);
    });
  }

  limitChange(limit) {
    getLogFromBackend().then(() => {
      // console.log('数据加载完成');
    });
    showNotification(`已设置为每页显示 ${limit} 行`, 3);
  }

  selectLimit(limit) {
    if (limit === this.currentLimit) return;

    this.currentLimit = limit;
    localStorage.setItem("limit", limit);

    // 更新显示
    this.updateCurrentLimit();

    // 隐藏下拉框
    this.hideOptions();

    // 执行回调函数
    this.limitChange(limit);
  }

  bindEvents() {
    const currentBox = document.getElementById("limitCurrent");
    const optionsBox = document.getElementById("limitOptions");
    const selector = document.getElementById("limitSelector");

    // 点击当前框切换下拉框显示
    currentBox.addEventListener("click", (e) => {
      e.stopPropagation();
      selector.classList.toggle("active");
    });

    // 点击其他地方关闭下拉框
    document.addEventListener("click", (e) => {
      if (!selector.contains(e.target)) {
        selector.classList.remove("active");
      }
    });

    // 键盘导航支持
    currentBox.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        selector.classList.toggle("active");
      }
      if (e.key === "Escape") {
        selector.classList.remove("active");
      }
    });
  }

  showOptions() {
    document.getElementById("limitSelector").classList.add("active");
  }

  hideOptions() {
    document.getElementById("limitSelector").classList.remove("active");
  }

  // 外部调用方法
  setLimit(limit) {
    if (this.limitOptions.includes(limit)) {
      this.selectLimit(limit);
    }
  }

  getLimit() {
    return this.currentLimit;
  }
}

// 初始化风格切换按钮
function InitializeThemeButton() {
  // 按钮切换模式
  const themeToggleButton = document.getElementById("theme-toggle-btn");
  const docElement = document.documentElement;

  function updateTheme(isDarkMode) {
    docElement.classList.toggle("dark", isDarkMode);
    themeToggleButton.setAttribute("aria-checked", isDarkMode);
    const newLabel = isDarkMode ? "切换到亮色主题" : "切换到暗色主题";
    themeToggleButton.setAttribute("aria-label", newLabel);
    try {
      localStorage.setItem("app-theme", isDarkMode ? "dark" : "light");
    } catch (e) {
      console.warn("Could not save theme to localStorage.", e);
    }
  }

  function handleThemeToggleClick() {
    const isDarkMode = docElement.classList.contains("dark");
    updateTheme(!isDarkMode);
  }

  function initializeTheme() {
    const isDarkMode = docElement.classList.contains("dark");
    updateTheme(isDarkMode);
  }

  themeToggleButton.addEventListener("click", handleThemeToggleClick);
  initializeTheme();
}

//发送通知
function showNotification(message, second = undefined) {
  // 移除旧的通知
  const oldNotification = document.querySelector(".limit-notification");
  if (oldNotification) oldNotification.remove();

  // 创建新通知
  const notification = document.createElement("div");
  notification.className = "limit-notification";
  notification.textContent = message;
  notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: #48bb78;
        color: white;
        padding: 10px 20px;
        border-radius: 6px;
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;

  document.body.appendChild(notification);

  // 3秒后自动消失
  const s = (second) ? second * 1000 : 20000
  setTimeout(() => {
    notification.style.animation = "slideOut 0.3s ease";
    setTimeout(() => notification.remove(), 300);
  }, s);
}

// 初始化回到最上层按钮
function initBackToTopBtn() {
  // 获取按钮
  const backToTopBtn = document.getElementById('backToTopBtn');
  
  // 显示/隐藏按钮的逻辑
  function toggleBackToTopButton() {
      if (window.scrollY > 300) {
          backToTopBtn.classList.add('show');
      } else {
          backToTopBtn.classList.remove('show');
      }
  }
  
  // 返回顶部函数
  function scrollToTop() {
      // 平滑滚动效果
      window.scrollTo({
          top: 0,
          behavior: 'smooth'
      });
      
      // 添加点击反馈
      backToTopBtn.style.transform = 'scale(0.95)';
      
      setTimeout(() => {
          backToTopBtn.style.transform = '';
          backToTopBtn.style.backgroundColor = '';
      }, 200);
  }
  
  // 添加滚动事件监听
  window.addEventListener('scroll', toggleBackToTopButton);
  
  // 添加点击事件监听
  backToTopBtn.addEventListener('click', scrollToTop);
  
  // 初始化检查
  toggleBackToTopButton();
  
  // 添加键盘快捷键支持（可选）
  document.addEventListener('keydown', function(event) {
      // 按 Home 键或 Ctrl + ↑ 返回顶部
      if (event.key === 'Home' || (event.ctrlKey && event.key === 'ArrowUp')) {
          event.preventDefault();
          scrollToTop();
      }
  });
}

// 从后端获取数据
async function getLogFromBackend() {
  try {
    // 从localStorage获取需要的数据
    var currentPage = parseInt(localStorage.getItem("currentPage")) || null;
    if (!currentPage) {
      localStorage.setItem("currentPage", 1);
      currentPage = 1;
    }
    var limit = parseInt(localStorage.getItem("limit")) || null;
    if (!limit) {
      localStorage.setItem("limit", 10);
      limit = 10;
    }

    const userPreferences = {
      page: currentPage,
      limit: limit,
    };

    // 发送AJAX请求到后端
    const response = await fetch("https://curator.ip-ddns.com:8000/api/data", {
      method: "POST",
      credentials: 'include',
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(userPreferences),
    });

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status}`);
    }

    const data = await response.json();
    if (currentPage != data.pagination.page) {
      currentPage = data.pagination.page;
      localStorage.setItem("currentPage", currentPage);
    }

    // 渲染页面数据
    window.logsTable.renderPage(data.data, data.count_risk);
    window.pageButtion.createPageButton(currentPage, data.pagination.maxpage);
    window.pageButtion.syncPageWidth();

  } catch (error) {
    console.error("加载数据失败:", error);
    showNotification(`加载数据失败: ${error}`);
  }
}

// 页面加载时初始化内容
document.addEventListener("DOMContentLoaded", function () {
  initBackToTopBtn()
  InitializeThemeButton();
  window.logsTable = new InitializeTable();
  window.pageButtion = new InitializePageButton();
  getLogFromBackend().then(() => {
    // console.log('数据加载完成');
  });
  window.limitSelector = new InitializeLimitSelector();
});
