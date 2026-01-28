import Foundation

/// 用户模型
struct User {
    let id: String
    let name: String
    let email: String
    
    /// 初始化用户
    init(id: String, name: String, email: String) {
        self.id = id
        self.name = name
        self.email = email
    }
}

/// 用户服务协议
protocol UserServiceProtocol {
    func getUser(id: String) -> User?
    func createUser(name: String, email: String) -> User
    func updateUser(_ user: User) -> Bool
}

/// 用户服务实现
class UserService: UserServiceProtocol {
    private var users: [String: User] = [:]
    
    func getUser(id: String) -> User? {
        return users[id]
    }
    
    func createUser(name: String, email: String) -> User {
        let id = UUID().uuidString
        let user = User(id: id, name: name, email: email)
        users[id] = user
        return user
    }
    
    func updateUser(_ user: User) -> Bool {
        guard users[user.id] != nil else {
            return false
        }
        users[user.id] = user
        return true
    }
}

/// 用户视图模型
class UserViewModel: ObservableObject {
    @Published var user: User?
    @Published var isLoading: Bool = false
    
    private let service: UserServiceProtocol
    
    init(service: UserServiceProtocol) {
        self.service = service
    }
    
    func loadUser(id: String) {
        isLoading = true
        user = service.getUser(id: id)
        isLoading = false
    }
}

/// 用户状态枚举
enum UserStatus {
    case active
    case inactive
    case suspended
}

/// 扩展 User 结构体
extension User {
    var displayName: String {
        return name.isEmpty ? email : name
    }
}
