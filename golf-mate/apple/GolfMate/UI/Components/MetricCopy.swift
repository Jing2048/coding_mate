import SwiftUI

/// Maps commercial metric / finding codes to Chinese-primary product labels.
enum MetricCopy {
    static func title(for name: String) -> String {
        switch name {
        case "tempo_s": return "站位至击球"
        case "backswing_s": return "上杆时长"
        case "downswing_s": return "下杆时长"
        case "rhythm": return "节奏比"
        case "peak_omega_rad_s": return "峰值角速度"
        case "peak_omega_to_impact_s": return "峰值到击球"
        case "hand_speed_peak_m_s": return "手腕峰值速度"
        case "plane_angle_deg": return "挥杆平面角"
        case "trajectory_radius_m": return "腕部轨迹半径"
        case "wrist_fe_impact_deg": return "击球腕屈伸"
        case "wrist_fe_delta_address_to_impact_deg": return "站位至击球腕角变化"
        case "wrist_ru_impact_deg": return "击球腕尺桡"
        case "clubface_impact_deg": return "击球杆面角"
        case "shaft_lean_impact_deg": return "击球杆身前倾"
        case "x_factor_top_deg": return "顶点 X-Factor"
        case "x_factor_proxy_deg": return "X-Factor 代理"
        case "sequence_score_proxy": return "发力顺序评分"
        case "casting_onset_s": return "提前释放时刻"
        case "segment_twist_rate_proxy_rad_s": return "节段扭转速率"
        case "high_order_residual": return "高阶残差"
        case "closure_rate_rad_s": return "闭合速率"
        default:
            return name
                .replacingOccurrences(of: "_", with: " ")
        }
    }

    static func findingTitle(for code: String) -> String {
        switch code {
        case "rhythm_too_fast_backswing": return "上杆偏快"
        case "rhythm_too_slow_backswing": return "上杆偏慢"
        case "rhythm_ok": return "节奏正常"
        case "casting_proxy": return "提前释放倾向"
        case "late_peak_omega": return "峰值角速度偏晚"
        case "release_timing_ok": return "释放时机正常"
        case "plane_flat_proxy": return "平面偏平"
        case "plane_steep_proxy": return "平面偏陡"
        case "tempo_very_fast": return "挥杆过快"
        case "release_early_proxy": return "释放偏早"
        case "release_abrupt_proxy": return "释放偏急"
        case "release_morphology_ok": return "释放形态正常"
        case "pro_manifold_outlier": return "与参考形态偏离"
        case "wrist_extends_into_impact": return "击球时腕伸"
        case "wrist_bows_into_impact": return "击球时腕屈"
        case "clubface_open_impact": return "击球面偏开"
        case "clubface_closed_impact": return "击球面偏闭"
        case "kinematic_sequence_out_of_order": return "发力顺序异常"
        case "reference_near_band": return "接近参考区间"
        case "reference_mild_deviation": return "轻度偏离参考"
        case "reference_large_deviation": return "明显偏离参考"
        default:
            return code
                .replacingOccurrences(of: "_", with: " ")
        }
    }

    static func findingBody(for code: String, fallback: String) -> String {
        switch code {
        case "rhythm_too_fast_backswing":
            return "上杆相对下杆偏快。下一杆只关注过渡是否更从容。"
        case "rhythm_too_slow_backswing":
            return "上杆相对下杆偏长。保持动作完整，同时减少无效停留。"
        case "casting_proxy", "release_early_proxy":
            return "腕部峰值角速度出现偏早，这是提前释放的代理信号，并非杆面实测。"
        case "late_peak_omega":
            return "峰值角速度出现在击球之后，请先核对击球时刻与传感器质量。"
        case "plane_flat_proxy":
            return "本杆腕部路径投影相对个人参考偏平。"
        case "plane_steep_proxy":
            return "本杆腕部路径投影相对个人参考偏陡。"
        case "tempo_very_fast":
            return "站位至击球时间明显偏短，建议下一杆降低启动急促感。"
        case "release_abrupt_proxy":
            return "腕部节段扭转在击球附近变化较急，属于代理判断。"
        case "pro_manifold_outlier":
            return "本杆波形与参考分布差异较大，不代表单一动作一定错误。"
        case "wrist_extends_into_impact":
            return "模型推断击球附近腕伸增加；该指标不是腕关节直接测量。"
        case "wrist_bows_into_impact":
            return "模型推断击球附近腕屈增加；该指标不是腕关节直接测量。"
        case "clubface_open_impact":
            return "模型推断杆面偏开；不可替代 Launch Monitor 杆面数据。"
        case "clubface_closed_impact":
            return "模型推断杆面偏闭；不可替代 Launch Monitor 杆面数据。"
        case "kinematic_sequence_out_of_order":
            return "模型推断近端到远端的峰值顺序异常，需结合视频或教练判断。"
        default:
            return fallback
        }
    }

    static func reason(_ raw: String) -> String {
        switch raw {
        case "low_confidence", "confidence_below_threshold": return "置信度不足"
        case "value_unavailable", "high_order_unavailable": return "当前数据不足以可靠输出"
        case "outside_calib_envelope": return "超出模型校准范围"
        case "scalar_mae_above_degraded_budget": return "该指标的校准误差过高"
        case "near_calib_edge": return "接近模型校准边界"
        case "missing_phases": return "阶段定位不完整"
        case "trajectory_invalid", "trajectory_unavailable": return "腕部轨迹质量不足"
        case "strap_slip_detected": return "检测到表带可能滑动"
        case "sensor_saturation": return "传感器出现饱和"
        case "impact_unavailable": return "无法可靠定位击球时刻"
        case "impact_kinematic_not_collision": return "击球时刻来自运动学代理"
        case "casting_timing_proxy": return "基于腕部时机代理"
        case "biomech_linear_proxy": return "基于单腕生物力学代理"
        case "segment_twist_not_clubface_closure": return "节段扭转不等于杆面闭合"
        default: return "质量门未通过"
        }
    }

    static func cue(_ raw: String?) -> String {
        switch raw {
        case "hold_current": return "保持当前节奏"
        case "tempo_slow_down": return "放慢启动"
        case "tempo_speed_up": return "缩短节奏"
        case "rhythm_smooth_transition": return "让过渡更平顺"
        case "rhythm_lengthen_backswing": return "给上杆更多时间"
        case "release_delay": return "延后释放"
        case "release_earlier": return "释放稍早一些"
        case "peak_omega_build": return "逐步建立速度"
        case "peak_omega_ease": return "减少峰值用力"
        case "plane_flatten": return "让腕部路径更平"
        case "plane_steepen": return "让腕部路径更陡"
        case "path_radius_stable": return "保持腕部路径半径"
        case "hand_speed_match": return "匹配个人手速"
        default: return "本杆不提供纠偏"
        }
    }

    static func formatValue(
        _ value: Double?,
        units: String,
        digits: Int = 2
    ) -> String {
        guard let value else { return "—" }
        let formatted = String(format: "%.\(digits)f", value)
        if units.isEmpty { return formatted }
        return "\(formatted) \(units)"
    }

    static func displayUnits(for name: String, raw: String) -> String {
        if name == "rhythm" { return "×" }
        if raw == "deg" { return "°" }
        if raw == "1" { return "" }
        return raw
    }

    static func digits(for units: String) -> Int {
        switch units {
        case "°", "deg", "rad/s", "m/s": return 1
        case "s", "×", "": return 2
        default: return 2
        }
    }
}
